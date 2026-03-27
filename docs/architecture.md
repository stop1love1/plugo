# Architecture

This document describes the high-level architecture of Plugo and how its components work together.

## Overview

Plugo is a monorepo with three main components:

```
┌─────────────────────────────────────────────────────────┐
│                    Customer Website                      │
│                                                         │
│  ┌───────────────┐                                      │
│  │  Chat Widget   │  <script src="widget.js">           │
│  │  (Preact)      │                                     │
│  └───────┬───────┘                                      │
└──────────┼──────────────────────────────────────────────┘
           │ WebSocket
           ▼
┌──────────────────────────────────────────────┐
│              Backend (FastAPI)                │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │  Router   │  │  Agent   │  │  Crawler   │  │
│  │  (API)    │──│  (LLM)   │  │  (HTTP)    │  │
│  └──────────┘  └────┬─────┘  └─────┬─────┘  │
│                     │              │         │
│            ┌────────┼──────────────┘         │
│            ▼        ▼                        │
│  ┌──────────┐  ┌──────────┐                  │
│  │ ChromaDB  │  │ Provider │                  │
│  │ (Vectors) │  │ Factory  │                  │
│  └──────────┘  └────┬─────┘                  │
│                     │                        │
│           ┌─────────┼─────────┐              │
│           ▼         ▼         ▼              │
│       Claude    OpenAI    Gemini   Ollama    │
└──────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────┐
│  Dashboard (React)    │
│  Management UI        │
└──────────────────────┘
```

## Components

### 1. Widget (`widget/`)

A lightweight (~50KB) Preact chat widget that gets embedded into customer websites via a `<script>` tag.

**Key design decisions:**
- **Preact over React** — smaller bundle size, critical for a third-party embed
- **WebSocket over HTTP polling** — real-time streaming of LLM responses
- **Shadow DOM ready** — styles are isolated from the host page
- **Page context** — sends the current page URL and content to the backend for context-aware responses

**Data flow:**
1. Widget initializes with a site token from `window.PlugoConfig`
2. Opens a WebSocket connection to `/ws/chat/{token}`
3. Receives greeting message and config (colors, position)
4. Sends user messages with page context
5. Receives streamed tokens and renders them incrementally

### 2. Backend (`backend/`)

Python FastAPI server that handles all business logic.

#### Agent (`agent/`)

The core intelligence layer:

- **`core.py` — ChatAgent**: Orchestrates the two operating modes:
  - *Knowledge mode*: Retrieves relevant content via RAG and answers questions
  - *Action mode*: Calls external APIs via tool execution
- **`rag.py` — RAGEngine**: ChromaDB-based vector search for finding relevant knowledge chunks
- **`tools.py` — ToolExecutor**: HTTP client that executes API tool calls on behalf of users

#### Providers (`providers/`)

Multi-LLM support via a factory pattern:

- `base.py` — Abstract base class defining the LLM interface (`stream`, `chat`, `embed`)
- `factory.py` — Factory function that instantiates the correct provider
- `claude_provider.py` — Anthropic Claude integration
- `openai_provider.py` — OpenAI GPT integration
- `gemini_provider.py` — Google Gemini integration
- `ollama_provider.py` — Local Ollama integration

#### Knowledge (`knowledge/`)

- `crawler.py` — Web crawler that extracts text content, chunks it, generates embeddings, and stores in ChromaDB
- `vector.py` — ChromaDB vector store wrapper

#### Repositories (`repositories/`)

Data access layer with swappable backends:

- `base.py` — Abstract repository interface
- `sqlite_repo.py` — SQLite implementation (development)
- `mongo_repo.py` — MongoDB implementation (production)

#### Routers (`routers/`)

API endpoints:

| Router | Endpoints | Purpose |
|--------|-----------|---------|
| `chat.py` | `WS /ws/chat/{token}` | Real-time chat via WebSocket |
| `sites.py` | `CRUD /api/sites` | Site management |
| `crawl.py` | `/api/crawl/*` | Crawl operations |
| `knowledge.py` | `/api/knowledge` | Knowledge base management |
| `tools.py` | `CRUD /api/tools` | API tool configuration |
| `sessions.py` | `/api/sessions` | Chat session history |

### 3. Dashboard (`dashboard/`)

React + Tailwind management UI for site owners.

**Pages:**
- **Sites** — List and create sites
- **Setup** — Configure crawling, view crawl status and history
- **Knowledge** — Browse crawled content chunks
- **Tools** — Configure API tools for Action mode
- **Embed** — Generate embed code snippet
- **Chat Log** — View chat session history
- **Settings** — LLM provider and model configuration

## Data Flow

### Chat Message Flow

```
User types message
    → Widget sends via WebSocket { message, pageContext }
    → Backend receives in chat router
    → ChatAgent builds system prompt:
        1. Retrieves page context (current URL, page content)
        2. Queries ChromaDB for relevant knowledge chunks (RAG)
        3. Loads configured API tools for the site
    → LLM provider streams response tokens
    → Each token sent back via WebSocket
    → Widget renders tokens incrementally
```

### Crawl Flow

```
Admin clicks "Start Crawl" in Dashboard
    → POST /api/crawl/start
    → WebCrawler starts async crawl:
        1. Fetches pages starting from site URL
        2. Extracts text (removes nav, footer, ads)
        3. Chunks text into ~500 token segments
        4. Generates embeddings via OpenAI
        5. Stores chunks in ChromaDB + database
    → Progress updates via polling /api/crawl/status
```

### Tool Execution Flow

```
User asks bot to perform an action
    → LLM decides to call a tool
    → ToolExecutor makes HTTP request to configured API
    → Result returned to LLM
    → LLM formulates response based on API result
    → Response streamed to user
```

## Database Schema

### Sites
| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique identifier |
| name | string | Site display name |
| url | string | Site URL |
| token | string | Auth token for widget |
| llm_provider | string | LLM provider name |
| llm_model | string | Model identifier |
| greeting | string | Welcome message |
| primary_color | string | Widget theme color |
| position | string | Widget position |

### Knowledge Chunks
| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique identifier |
| site_id | string | Parent site |
| content | string | Text content |
| source_url | string | Source page URL |
| title | string | Page title |
| embedding_id | string | ChromaDB reference |

### Tools
| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique identifier |
| site_id | string | Parent site |
| name | string | Tool name for LLM |
| description | string | What the tool does |
| method | string | HTTP method |
| url | string | API endpoint URL |
| params_schema | object | Parameter definitions |
| auth_type | string | bearer / api_key / none |
