# Plugo — Claude Code Project Guide

## Project Overview

Plugo is an embeddable AI chat widget platform. It has three components:
- **backend/** — Python FastAPI (port 8000)
- **dashboard/** — React + Tailwind management UI (port 3000/5173)
- **widget/** — Preact embeddable chat widget (~50KB)

## Quick Commands

```bash
make setup          # One-time: create venv, install all deps
make dev            # Start all 3 services concurrently
make test           # Run all tests
make lint           # Run all linters
make format         # Format all code
make check          # Run lint + format-check + typecheck
```

## Code Style

### Python (backend/)
- **Formatter/Linter**: Ruff (config in `pyproject.toml`)
- Line length: 120
- Use type hints for all function signatures
- Use `async/await` for I/O operations
- FastAPI dependency injection via `Depends()`
- Run: `make lint-fix` and `make format` before committing

### TypeScript (dashboard/ + widget/)
- **Linter**: ESLint (flat config in each `eslint.config.js`)
- **Formatter**: Prettier (config in root `.prettierrc`)
- **Testing**: Vitest + Testing Library
- Functional components with hooks
- TanStack Query for server state, Zustand for client state

## Architecture Patterns

- **Repository pattern**: `backend/repositories/` — swap SQLite/MongoDB via env var
- **Provider factory**: `backend/providers/factory.py` — swap LLM providers
- **RAG pipeline**: Crawl → chunk → embed → ChromaDB → query at chat time
- **Tool calling**: LLM decides to call HTTP APIs configured per site

## Testing

- Backend tests: `backend/tests/` (pytest + pytest-asyncio)
- Dashboard tests: `dashboard/src/tests/` (Vitest + Testing Library)
- Widget tests: `widget/src/**/*.test.ts` (Vitest)
- Always run `make test` before creating a PR

## Important Files

- `backend/agent/core.py` — Main ChatAgent orchestrator
- `backend/knowledge/crawler.py` — Web crawler with graceful stop
- `backend/providers/base.py` — LLM provider interface
- `widget/src/ui/App.tsx` — Widget entry point
- `dashboard/src/App.tsx` — Dashboard router

## Environment

- Python deps in `.venv/` (project-local)
- Node deps in `node_modules/` (per package)
- Config via `.env` (never commit this file)
- Database: SQLite (dev) or MongoDB (prod) — set `DATABASE_PROVIDER`
