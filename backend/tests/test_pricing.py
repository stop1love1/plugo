"""Tests for the model pricing table and cost estimator (backend/utils/pricing.py)."""

from utils.pricing import estimate_cost


def test_gemini_model_yields_non_zero_cost() -> None:
    """Before the fix, any Gemini model fell through to the `default` (0.0, 0.0)
    entry and every Gemini site reported $0.00 cost regardless of usage."""

    cost = estimate_cost("gemini-1.5-flash", input_tokens=1_000_000, output_tokens=1_000_000)

    assert cost > 0.0


def test_unpriced_model_still_falls_back_to_default_zero() -> None:
    """A model with no matching entry (e.g. a local Ollama model) should still
    resolve to the explicit `default` (0.0, 0.0) rather than raising."""

    assert estimate_cost("llama3", input_tokens=1_000_000, output_tokens=1_000_000) == 0.0


def test_longest_prefix_match_prefers_gpt_4o_mini_over_gpt_4o() -> None:
    """`gpt-4o-mini` must resolve to the mini price, not the (shorter-prefix)
    `gpt-4o` price — this is the longest-prefix-match property the lookup relies on."""

    mini_cost = estimate_cost("gpt-4o-mini-2024-07-18", input_tokens=1_000_000, output_tokens=1_000_000)
    full_cost = estimate_cost("gpt-4o-2024-08-06", input_tokens=1_000_000, output_tokens=1_000_000)

    assert mini_cost > 0.0
    assert full_cost > 0.0
    assert mini_cost != full_cost
    assert mini_cost < full_cost
