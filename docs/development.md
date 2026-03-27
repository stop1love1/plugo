# Development Guide

This guide covers everything you need to set up a local development environment for Plugo.

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend |
| Node.js | 18+ | Dashboard & Widget |
| Docker | 24+ | Optional, for full-stack dev |
| Git | 2.30+ | Version control |

## Quick Start

```bash
# Clone the repository
git clone https://github.com/stop1love1/plugo.git
cd plugo

# Create environment file
cp .env.example .env
# Edit .env and add your API keys

# Install all dependencies
make install

# Start services (pick one)
make up          # Docker (all-in-one)
make backend     # Backend only (local)
make dashboard   # Dashboard only (local)
```

## Project Structure

```
plugo/
├── backend/              # Python FastAPI backend
│   ├── main.py           # Application entry point
│   ├── config.py         # Settings (from env vars)
│   ├── database.py       # SQLite initialization
│   ├── agent/            # AI agent logic
│   │   ├── core.py       # ChatAgent — main orchestrator
│   │   ├── rag.py        # RAG engine (ChromaDB)
│   │   └── tools.py      # External API tool executor
│   ├── knowledge/        # Content ingestion
│   │   ├── crawler.py    # Web crawler
│   │   └── vector.py     # Vector store operations
│   ├── models/           # Database models (SQLAlchemy)
│   ├── providers/        # LLM provider implementations
│   │   ├── base.py       # Abstract interface
│   │   ├── factory.py    # Provider factory
│   │   ├── claude_provider.py
│   │   ├── openai_provider.py
│   │   ├── gemini_provider.py
│   │   └── ollama_provider.py
│   ├── repositories/     # Data access layer
│   │   ├── base.py       # Abstract repository
│   │   ├── sqlite_repo.py
│   │   └── mongo_repo.py
│   └── routers/          # API route handlers
│       ├── chat.py       # WebSocket chat endpoint
│       ├── sites.py      # Site CRUD
│       ├── crawl.py      # Crawl management
│       ├── knowledge.py  # Knowledge base
│       ├── tools.py      # API tools
│       └── sessions.py   # Chat sessions
├── widget/               # Preact embeddable widget
│   ├── src/
│   │   ├── index.ts      # Widget bootstrap
│   │   ├── lib/
│   │   │   └── websocket.ts  # WebSocket client
│   │   └── ui/
│   │       ├── App.tsx       # Main app component
│   │       ├── Bubble.tsx    # Chat bubble button
│   │       ├── Window.tsx    # Chat window
│   │       └── Message.tsx   # Message renderer
│   └── vite.config.ts
├── dashboard/            # React management UI
│   ├── src/
│   │   ├── App.tsx       # Router setup
│   │   ├── lib/
│   │   │   ├── api.ts    # Axios API client
│   │   │   └── store.ts  # Zustand state
│   │   ├── components/
│   │   │   └── Layout.tsx
│   │   └── pages/        # Dashboard pages
│   └── vite.config.ts
├── docs/                 # Documentation
├── examples/             # Usage examples
└── docker-compose.yml
```

## Backend Development

### Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000` with auto-reload on file changes.

### API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Database

**SQLite (default):** No setup required. Database file is created at `data/plugo.db`.

**MongoDB:** Set `DATABASE_PROVIDER=mongodb` in `.env` and ensure MongoDB is running:
```bash
docker run -d -p 27017:27017 mongo:7
```

### Adding a New LLM Provider

1. Create `backend/providers/your_provider.py` implementing `BaseLLMProvider`
2. Add the provider to `backend/providers/factory.py`
3. Add configuration to `backend/config.py`
4. Update `.env.example` with new environment variables

### Adding a New API Router

1. Create `backend/routers/your_router.py` with an `APIRouter`
2. Register it in `backend/main.py` via `app.include_router()`

## Dashboard Development

### Setup & Run

```bash
cd dashboard
npm install
npm run dev
```

The dashboard will be available at `http://localhost:5173` with hot module replacement.

### Tech Stack

- **React 18** — UI framework
- **Vite** — Build tool
- **Tailwind CSS** — Styling
- **TanStack Query** — Server state management
- **Zustand** — Client state management
- **React Router** — Routing
- **Axios** — HTTP client
- **Lucide** — Icons

### Adding a New Page

1. Create `dashboard/src/pages/YourPage.tsx`
2. Add the route in `dashboard/src/App.tsx`
3. Add navigation link in `dashboard/src/components/Layout.tsx`

## Widget Development

### Setup & Run

```bash
cd widget
npm install
npm run dev      # Dev server with HMR
npm run build    # Production build
```

### Tech Stack

- **Preact** — Lightweight React alternative (~3KB)
- **TypeScript** — Type safety
- **Vite** — Build tool (outputs single `widget.js` file)

### Testing the Widget

Open `examples/demo.html` in a browser, or embed in any HTML page:

```html
<script>
  window.PlugoConfig = {
    token: "YOUR_SITE_TOKEN",
    serverUrl: "ws://localhost:8000",
  };
</script>
<script src="http://localhost:8000/static/widget.js" async></script>
```

## Docker Development

### Start All Services

```bash
docker compose up --build
```

### View Logs

```bash
docker compose logs -f           # All services
docker compose logs -f backend   # Backend only
```

### Reset Everything

```bash
docker compose down -v   # Stops and removes all data volumes
```

## Common Tasks

| Task | Command |
|------|---------|
| Install all dependencies | `make install` |
| Start with Docker | `make up` |
| Stop Docker services | `make down` |
| Start backend (local) | `make backend` |
| Start dashboard (local) | `make dashboard` |
| Build widget | `make widget` |
| Build all | `make build` |
| View all commands | `make help` |

## Troubleshooting

### Widget not loading

- Check that the backend is running and serving `/static/widget.js`
- Verify the site token in `PlugoConfig` matches a valid site
- Check browser console for CORS errors — update `CORS_ORIGINS` in `.env`

### WebSocket connection failing

- Ensure the `serverUrl` in `PlugoConfig` uses the correct protocol (`ws://` or `wss://`)
- Check that port 8000 is accessible
- Behind a reverse proxy? Ensure WebSocket upgrade headers are forwarded

### Crawl not working

- Check that `OPENAI_API_KEY` is set (required for embeddings)
- Verify the target URL is accessible from the server
- Check crawl job status via `GET /api/crawl/status/{site_id}`

### LLM not responding

- Verify the API key for your chosen provider is correct
- Check backend logs for error messages
- Try switching to a different provider to isolate the issue
