# Plugo — Claude Code Project Guide

## Project Overview

Plugo is an embeddable AI chat widget platform with two components:
- **backend/** — Python FastAPI (port 8000)
- **frontend/** — React dashboard + Preact widget (port 3000)
  - `frontend/src/` — Dashboard (React + Vite + Tailwind)
  - `frontend/src/widget/` — Embeddable chat widget (Preact, ~50KB IIFE bundle)

## Quick Commands

```bash
make setup          # One-time: create venv, install all deps
make dev            # Start all services (backend + frontend)
make dev-backend    # Start backend only
make dev-frontend   # Start frontend only
make test           # Run all tests
make test-backend   # Run backend tests only
make test-frontend  # Run frontend tests only
make lint           # Run all linters
make lint-fix       # Run linters with auto-fix
make format         # Format all code
make check          # Run lint + format-check + typecheck
make build          # Build all production assets
make up             # Start with Docker Compose
make down           # Stop Docker services
```

## Admin Login

Admin credentials are configured in `config.json` → `auth.username` / `auth.password`.
Override via `.env` with `USERNAME` / `PASSWORD`.
Default: `plugo` / `pluginme`. Single admin only.

## Code Style

### Python (backend/)
- **Formatter/Linter**: Ruff (config in `pyproject.toml`)
- Line length: 120
- Use type hints for all function signatures
- Use `async/await` for I/O operations
- FastAPI dependency injection via `Depends()`
- Run: `make lint-fix` and `make format` before committing

### TypeScript (frontend/)
- **Linter**: ESLint (flat config in each `eslint.config.js`)
- **Formatter**: Prettier (config in root `.prettierrc`)
- **Testing**: Vitest + Testing Library
- Functional components with hooks
- TanStack Query for server state, Zustand for client state

## Architecture Patterns

- **Repository pattern**: `backend/repositories/` — swap SQLite/MongoDB via `config.json → database.provider`
- **Provider factory**: `backend/providers/factory.py` — swap LLM providers (claude, openai, gemini, ollama, lmstudio)
- **RAG pipeline**: Crawl → semantic chunk → embed → ChromaDB → query at chat time
- **Agent system**: `backend/agent/core.py` — ChatAgent with Knowledge Mode + Action Mode
- **Tool calling**: LLM decides to call HTTP APIs configured per site

## Testing

- Backend tests: `backend/tests/` (pytest + pytest-asyncio)
- Frontend tests: `frontend/src/tests/` (Vitest + Testing Library)
- Widget tests: `frontend/src/widget/**/*.test.ts` (Vitest)
- Always run `make test` before creating a PR

## Configuration

Two config files at project root:

- **`config.json`** — all project settings. Committed to repo.
- **`.env`** — secrets only (API keys, SECRET_KEY). Never committed.

```
config.json          ← project config (safe to commit)
├── llm.provider/model
├── ollama.base_url/model
├── embedding.provider/model/cache_size/cache_ttl
├── database.provider/url/mongodb_url/mongodb_database
├── vector_store.chroma_path
├── rag.min_score/max_chunks
├── server.backend_port/cors_origins/widget_cdn_url
├── auth.enabled
└── rate_limit.default/chat/crawl

.env                 ← secrets only
├── ANTHROPIC_API_KEY
├── OPENAI_API_KEY
├── GEMINI_API_KEY
├── SECRET_KEY
├── USERNAME
└── PASSWORD
```

Environment variables override both (for Docker/CI).

## Environment

- Python deps in `.venv/` (project-local)
- Node deps in `node_modules/` (per package in `frontend/`, managed with pnpm workspaces)
- Database: SQLite (dev) or MongoDB (prod) — set in `config.json → database.provider`
- Vector store: ChromaDB at `config.json → vector_store.chroma_path`
