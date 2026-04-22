"""Per-site origin validation for widget-facing public endpoints.

The global FastAPI CORSMiddleware in `main.py` is a coarse gate — it accepts
every origin configured in `server.cors_origins`. That's correct for the
admin dashboard but wrong for multi-tenant embedding: if site A allows
`a.com` globally, then `a.com` can also reach site B's public widget
endpoints. Tenant isolation must happen per-site, keyed on the site's own
`allowed_domains` list. This helper is the single source of truth for that
check — used by the SSE stream, the chat WebSocket, and any future public
widget route.
"""

from urllib.parse import urlparse


def validate_site_origin(site: dict, origin: str | None) -> bool:
    """Return True if `origin` is permitted to call endpoints scoped to `site`.

    Contract (mirrors the WS origin check at `routers/chat.py:113-124`):
      - If the site has no `allowed_domains` configured, any origin is allowed
        (including missing). This preserves the "not locked down" dev path.
      - If `allowed_domains` is set, the origin MUST be present and its host
        must equal one of the entries OR be a subdomain of one (`sub.example.com`
        matches `example.com`).
      - Empty strings and whitespace-only entries are ignored so a stray comma
        can't accidentally allow everyone.

    Security notes:
      - `Origin: null` (sent by sandboxed iframes, `file://` documents, and
        some cross-origin redirects) and a missing `Origin` header are BOTH
        denied when `allowed_domains` is non-empty. `urlparse("null").hostname`
        is `None`, which falls through to the no-hostname rejection branch.
        This is intentional: a site that opts in to a domain allowlist should
        never be reachable from an opaque origin that cannot be attributed.
      - When `allowed_domains` is empty the check is permissive by design
        (dev/ungated mode), so `null` is allowed in that case too.
    """
    allowed_domains = site.get("allowed_domains") if site else None
    if not allowed_domains:
        return True
    allowed = [d.strip() for d in str(allowed_domains).split(",") if d.strip()]
    if not allowed:
        return True
    if not origin:
        return False
    host = urlparse(origin).hostname
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in allowed)
