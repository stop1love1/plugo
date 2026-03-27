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
