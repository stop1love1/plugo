import httpx
from logging_config import logger
from utils.crypto import decrypt_value

from knowledge.crawler import _is_safe_public_url


class ToolExecutor:
    """Registry and executor for site-specific tools."""

    async def get_tools_for_site(self, repos, site_id: str) -> list[dict]:
        """Load all enabled tools for a site, formatted for LLM."""
        tools = await repos.tools.list_enabled_by_site(site_id)

        formatted = []
        for tool in tools:
            params = tool.get("params_schema", {})
            properties = {}
            required = []
            for name, schema in params.items():
                properties[name] = {
                    "type": schema.get("type", "string"),
                    "description": schema.get("description", ""),
                }
                if schema.get("required", False):
                    required.append(name)

            formatted.append({
                "name": tool["name"],
                "description": tool["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
                "_meta": {
                    "id": tool["id"],
                    "method": tool["method"],
                    "url": tool["url"],
                    "auth_type": tool.get("auth_type"),
                    "auth_value": self._decrypt_auth(tool.get("auth_value")),
                    "headers": tool.get("headers", {}),
                },
            })
        return formatted

    @staticmethod
    def _decrypt_auth(auth_value: str | None) -> str | None:
        """Decrypt an encrypted auth_value; None if decryption fails (key rotation / corrupted).

        Returning None rather than the raw ciphertext stops us from silently sending
        an undecryptable value as a bearer token in an outbound HTTP call.
        """
        if not auth_value:
            return auth_value
        try:
            return decrypt_value(auth_value)
        except ValueError as e:
            logger.warning("Tool auth_value decryption failed", error=str(e))
            return None

    async def execute_tool(
        self,
        tool_meta: dict,
        arguments: dict,
        timeout: float = 30.0,
    ) -> dict:
        """Execute an HTTP tool call and return the result."""
        method = tool_meta["method"].upper()
        url = tool_meta["url"]
        headers = dict(tool_meta.get("headers", {}))

        # SSRF guard: tool URLs are admin-configured but revalidated at execution time
        # (DNS rebinding defense). Tools never get the allow_private escape hatch.
        safe, reason = await _is_safe_public_url(url, allow_private=False)
        if not safe:
            logger.warning("Blocked tool execution due to unsafe URL", url=url, reason=reason)
            return {"error": f"Blocked unsafe tool URL: {reason}", "success": False}

        if tool_meta.get("auth_type") == "bearer" and tool_meta.get("auth_value"):
            headers["Authorization"] = f"Bearer {tool_meta['auth_value']}"
        elif tool_meta.get("auth_type") == "api_key" and tool_meta.get("auth_value"):
            headers["X-API-Key"] = tool_meta["auth_value"]

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    response = await client.get(url, params=arguments, headers=headers)
                elif method == "POST":
                    response = await client.post(url, json=arguments, headers=headers)
                elif method == "PUT":
                    response = await client.put(url, json=arguments, headers=headers)
                elif method == "DELETE":
                    response = await client.delete(url, params=arguments, headers=headers)
                else:
                    return {"error": f"Unsupported method: {method}"}

                try:
                    data = response.json()
                except Exception:
                    data = response.text

                return {
                    "status_code": response.status_code,
                    "data": data,
                    "success": 200 <= response.status_code < 300,
                }
        except httpx.TimeoutException:
            return {"error": "Request timed out", "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}


tool_executor = ToolExecutor()
