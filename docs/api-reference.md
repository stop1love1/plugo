# API Reference

Base URL: `http://localhost:8000`

Interactive API documentation is available at `/docs` (Swagger UI) when the backend is running.

## Table of Contents

- [Health Check](#health-check)
- [Sites](#sites)
- [Chat (WebSocket)](#chat-websocket)
- [Crawl](#crawl)
- [Knowledge](#knowledge)
- [Tools](#tools)
- [Sessions](#sessions)
- [Rate Limits](#rate-limits)

---

## Health Check

### `GET /health`

Returns server health status.

**Response:**
```json
{
  "status": "ok",
  "database": "sqlite"
}
```

---

## Sites

### `POST /api/sites`

Create a new site.

**Request body:**
```json
{
  "name": "My Website",
  "url": "https://example.com",
  "greeting": "Hello! How can I help you?",
  "primary_color": "#6366f1",
  "position": "bottom-right",
  "llm_provider": "claude",
  "llm_model": "claude-sonnet-4-20250514"
}
```

**Response:**
```json
{
  "id": "site_abc123",
  "name": "My Website",
  "url": "https://example.com",
  "token": "generated-token-here",
  "greeting": "Hello! How can I help you?",
  "primary_color": "#6366f1",
  "position": "bottom-right",
  "llm_provider": "claude",
  "llm_model": "claude-sonnet-4-20250514"
}
```

### `GET /api/sites`

List all sites.

### `GET /api/sites/{site_id}`

Get a specific site by ID.

### `PUT /api/sites/{site_id}`

Update a site.

### `DELETE /api/sites/{site_id}`

Delete a site and all associated data.

---

## Chat (WebSocket)

### `WS /ws/chat/{site_token}`

Real-time chat endpoint using WebSocket.

**Connection flow:**

1. Client connects with site token
2. Server sends `connected` message with greeting and config
3. Client sends messages, server streams responses

**Server → Client messages:**

```json
// Connection established
{ "type": "connected", "session_id": "...", "greeting": "...", "config": { "primaryColor": "#6366f1", "position": "bottom-right" } }

// Response streaming started
{ "type": "start" }

// Response token (streamed incrementally)
{ "type": "token", "content": "Hello" }

// Response streaming ended
{ "type": "end" }

// Error occurred
{ "type": "error", "message": "Error description" }
```

**Client → Server messages:**

```json
{
  "message": "What products do you offer?",
  "pageContext": {
    "url": "https://example.com/products",
    "title": "Our Products",
    "pageText": "First 1500 chars of page content..."
  }
}
```

---

## Crawl

### `POST /api/crawl/start`

Start crawling a website.

**Request body:**
```json
{
  "site_id": "site_abc123",
  "url": "https://example.com",
  "max_pages": 50
}
```

### `POST /api/crawl/stop/{site_id}`

Stop an active crawl. Data already crawled will be saved.

### `GET /api/crawl/status/{site_id}`

Get current crawl status.

**Response:**
```json
{
  "crawl_enabled": true,
  "crawl_status": "running",
  "knowledge_count": 142,
  "last_crawled_at": "2024-01-15T10:30:00Z"
}
```

### `GET /api/crawl/jobs/{site_id}`

List crawl job history.

### `PUT /api/crawl/toggle/{site_id}`

Enable or disable crawling for a site.

**Request body:**
```json
{
  "enabled": true,
  "max_pages": 50
}
```

### `DELETE /api/crawl/knowledge/{site_id}`

Delete all crawled knowledge data for a site.

---

## Knowledge

### `GET /api/knowledge?site_id={site_id}`

List knowledge chunks for a site.

**Query parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `site_id` | string | required | Site ID |
| `page` | int | 1 | Page number |
| `limit` | int | 20 | Items per page |

---

## Tools

### `POST /api/tools`

Add an API tool for a site.

**Request body:**
```json
{
  "site_id": "site_abc123",
  "name": "search_products",
  "description": "Search for products by keyword",
  "method": "GET",
  "url": "https://api.example.com/products/search",
  "params_schema": {
    "query": {
      "type": "string",
      "description": "Search keyword",
      "required": true
    },
    "limit": {
      "type": "integer",
      "description": "Max results to return",
      "required": false
    }
  },
  "auth_type": "bearer",
  "auth_value": "your-api-key"
}
```

### `GET /api/tools?site_id={site_id}`

List all tools for a site.

### `PUT /api/tools/{tool_id}`

Update a tool.

### `DELETE /api/tools/{tool_id}`

Delete a tool.

---

## Sessions

### `GET /api/sessions?site_id={site_id}`

List chat sessions for a site.

**Query parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `site_id` | string | required | Site ID |
| `page` | int | 1 | Page number |
| `limit` | int | 20 | Items per page |

### `GET /api/sessions/{session_id}`

Get a specific chat session with its messages.

---

## Rate Limits

Rate-limited requests are refused with **HTTP 429**. Every limit is configured in
`config.json` → `rate_limit`, and a change takes effect on backend restart. The
dashboard exposes the two tenant-facing values under **Global Settings → Rate Limiting**.

> **These limits bind for the first time in this version.** They were configured but
> inert in earlier releases (see [Upgrading](deployment.md#upgrading-rate-limits-now-bind)).
> If you drive Plugo from your own backend rather than the widget, size
> `rate_limit.chat` for your integration before upgrading.

### Limited routes

Only three routes carry a limit at all — everything else is unlimited and relies on
authentication. Two of the three carry two limits each, one row per limit below.

| Route | Keyed by | Default | `config.json` key |
|-------|----------|---------|-------------------|
| `POST /api/chat/{site_token}/stream` | site token — **whole tenant**, all its callers share one bucket | `60/minute` | `rate_limit.chat` |
| `POST /api/chat/{site_token}/stream` | client IP | `120/minute` | `rate_limit.public_ip` |
| `POST /api/sessions/{session_id}/feedback` | site token — whole tenant | `60/minute` | `rate_limit.default` |
| `POST /api/sessions/{session_id}/feedback` | client IP | `120/minute` | `rate_limit.public_ip` |
| `POST /api/auth/login` | client IP | `5/minute` | `rate_limit.auth` |

The two public routes carry **both** of their limits at once, and a request must satisfy
each. The token-keyed limit is tenant fairness; the IP-keyed one is the ceiling a caller
who rotates the site token cannot shed. A tenant-keyed limit is spent by all of that
tenant's visitors together — it is not per visitor.

`POST /api/chat/{site_token}/stream` additionally caps **simultaneous open streams** per
site token (`rate_limit.sse_concurrent`, default `10`), which is a concurrency cap rather
than a rate: exceeding it also returns 429, with `"Too many concurrent streams"`.

The embedded widget reaches only the feedback route of the two — it chats over WebSocket,
but its thumbs-up/down buttons POST here, and it discards the response. A 429 on widget
feedback is therefore silent: no user-visible error, just feedback that never arrives.

### WebSocket

`WS /ws/chat/{site_token}` is not a slowapi route. Its limits are enforced per **message**,
and an over-limit message is answered with an in-band frame rather than a status code:

```json
{ "type": "error", "message": "Too many messages. Please slow down." }
```

| Limit | Keyed by | Default | `config.json` key |
|-------|----------|---------|-------------------|
| Per-session fairness | (site token, session id) | 20 per 60s | *not configurable — `WS_RATE_LIMIT_MAX` in `routers/chat.py`* |
| Per-address ceiling | client IP | `300/minute` | `rate_limit.ws_public_ip` |

Note that nothing limits how many WebSocket *connections* a client may open — only how
many messages it may send once connected.

### What one source can send in total

**slowapi buckets per endpoint, so these are not a shared pool.** A single client IP can
therefore spend every per-IP allowance concurrently:

| | Per minute | LLM turns? |
|---|---|---|
| `POST .../feedback` (`public_ip`) | 120 | no — a DB write |
| `POST .../stream` (`public_ip`) | 120 | yes |
| `WS /ws/chat/...` (`ws_public_ip`) | 300 | yes |
| **Total** | **540** | **420** |

No single config value expresses that total, and 420 LLM turns per minute per source is
the number to size provider spend against — not any one row above. Lowering the total
means lowering `public_ip` and `ws_public_ip` together.

Behind a reverse proxy, every visitor presents the proxy's address and shares one bucket
unless `FORWARDED_ALLOW_IPS` is set — see
[Environment Variables](deployment.md#environment-variables).
