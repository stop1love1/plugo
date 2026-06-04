"""Tool-calling capability must reflect what each provider actually implements.

Regression guard for the silent Action-mode failure: Gemini was *not* in
``no_tool_providers``, so the agent advertised tools and passed them to the
Gemini provider — which ignores them and always returns ``tool_calls: []``.
The capability now lives on the provider class (authoritative, can't drift),
combined with the ``no_tool_providers`` config as an admin override.
"""

from agent.core import ChatAgent


class _FakeProvider:
    """Minimal stand-in so we can pick a tool capability without touching an SDK."""

    def __init__(self, supports_tools: bool):
        self.supports_tools = supports_tools
        self.last_usage = None


def test_provider_classes_declare_tool_capability():
    from providers.claude_provider import ClaudeProvider
    from providers.gemini_provider import GeminiProvider
    from providers.ollama_provider import OllamaProvider
    from providers.openai_provider import OpenAIProvider

    assert ClaudeProvider.supports_tools is True
    assert OpenAIProvider.supports_tools is True
    # Not implemented in the current SDK path → must declare False so the agent
    # falls back to knowledge-only instead of silently dropping tool calls.
    assert GeminiProvider.supports_tools is False
    assert OllamaProvider.supports_tools is False


def test_agent_disables_tools_when_provider_cannot_call_them(monkeypatch):
    """'gemini' is NOT in no_tool_providers, yet an agent backed by a provider
    that declares supports_tools=False must not enable tool calling."""
    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _FakeProvider(supports_tools=False))
    agent = ChatAgent(site_id="s", site_name="n", site_url="https://x", llm_provider="gemini")
    assert agent.supports_tools is False


def test_agent_enables_tools_for_capable_provider(monkeypatch):
    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _FakeProvider(supports_tools=True))
    agent = ChatAgent(site_id="s", site_name="n", site_url="https://x", llm_provider="claude")
    assert agent.supports_tools is True


def test_config_no_tool_providers_overrides_capable_provider(monkeypatch):
    """no_tool_providers stays an admin kill-switch even for capable providers
    (e.g. lmstudio reuses the OpenAI provider but is listed as no-tool)."""
    monkeypatch.setattr("agent.core.get_llm_provider", lambda *a, **k: _FakeProvider(supports_tools=True))
    agent = ChatAgent(site_id="s", site_name="n", site_url="https://x", llm_provider="lmstudio")
    assert agent.supports_tools is False
