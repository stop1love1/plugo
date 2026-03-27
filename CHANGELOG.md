# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2024-01-01

### Added

- Embeddable chat widget (Preact, ~50KB) with WebSocket streaming
- FastAPI backend with multi-LLM support (Claude, OpenAI, Gemini, Ollama)
- Website crawler with automatic text extraction and chunking
- RAG engine using ChromaDB for vector search
- Tool calling system for API integrations (Action mode)
- Management dashboard (React + Tailwind)
  - Site management with token-based auth
  - Crawl control with start/stop and history
  - Knowledge base viewer
  - API tools configuration
  - Embed code generator
  - Chat session logs
  - Settings page (LLM provider, model selection)
- Multi-database support (SQLite for dev, MongoDB for production)
- Docker Compose setup for one-command deployment
- Page context awareness (widget sends current page info to bot)
