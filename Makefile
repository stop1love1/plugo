# ============================================
# Plugo — Development Commands
# ============================================
#
# Project structure:
#   - backend/  → Python (.venv/)
#   - frontend/ → React dashboard + Preact widget
#     - frontend/src/         → Dashboard (React)
#     - frontend/src/widget/  → Widget (Preact IIFE)
#
# Quick start:
#   make setup    # One-time setup
#   make dev      # Start everything
#
# ============================================

.PHONY: help setup install dev up down build clean logs lint format typecheck test check

# Detect OS for venv path
ifeq ($(OS),Windows_NT)
    VENV_BIN = .venv/Scripts
    PYTHON = .venv/Scripts/python
    PIP = .venv/Scripts/pip
else
    VENV_BIN = .venv/bin
    PYTHON = .venv/bin/python
    PIP = .venv/bin/pip
endif

# Default target
help: ## Show this help message
	@echo ""
	@echo "  Plugo - Embeddable AI Chat Widget"
	@echo "  =================================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ============================================================
# Setup & Install
# ============================================================

setup: ## Full project setup (venv + all deps + env file)
	@echo "==> Creating Python virtual environment..."
	python -m venv .venv || echo "venv already exists or python not found, skipping..."
	@echo "==> Installing backend dependencies..."
	$(PIP) install -r backend/requirements-dev.txt
	@echo "==> Installing frontend dependencies..."
	cd frontend && pnpm install
	@echo "==> Creating .env file..."
	cp -n .env.example .env 2>/dev/null || echo ".env already exists"
	@echo ""
	@echo "  Setup complete! Edit .env with your API keys, then run: make dev"
	@echo ""

install: ## Install all dependencies (assumes venv exists)
	$(PIP) install -r backend/requirements.txt
	cd frontend && pnpm install

install-dev: ## Install all dependencies including dev tools
	$(PIP) install -r backend/requirements-dev.txt
	cd frontend && pnpm install
	$(VENV_BIN)/pre-commit install

# ============================================================
# Development
# ============================================================

dev: ## Start all services (backend + frontend on 2 ports)
ifeq ($(OS),Windows_NT)
	npx --yes concurrently -n backend,frontend -c blue,green \
		".venv\\Scripts\\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend" \
		"cd frontend && pnpm dev"
else
	npx --yes concurrently -n backend,frontend -c blue,green \
		"$(PYTHON) -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend" \
		"cd frontend && pnpm dev"
endif

dev-backend: ## Start backend only
	$(PYTHON) -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend

dev-frontend: ## Start frontend (builds widget, then runs dashboard)
	cd frontend && pnpm dev

# ============================================================
# Docker
# ============================================================

up: ## Start all services with Docker Compose
	docker compose up --build -d

down: ## Stop all services
	docker compose down

logs: ## Show logs from all services
	docker compose logs -f

logs-backend: ## Show backend logs only
	docker compose logs -f backend

rebuild: ## Rebuild and restart all services
	docker compose down
	docker compose up --build -d

clean: ## Stop services and remove volumes (WARNING: deletes data)
	docker compose down -v

# ============================================================
# Build
# ============================================================

build: ## Build all production assets
	cd frontend && pnpm build

build-widget: ## Build widget only
	cd frontend && pnpm build:widget

# ============================================================
# Code Quality
# ============================================================

lint: ## Run all linters
	cd backend && ../$(VENV_BIN)/ruff check --config pyproject.toml .
	cd frontend && pnpm lint

lint-fix: ## Run all linters with auto-fix
	cd backend && ../$(VENV_BIN)/ruff check --config pyproject.toml --fix .
	cd frontend && pnpm lint:fix

format: ## Format all code
	cd backend && ../$(VENV_BIN)/ruff format --config pyproject.toml .
	cd frontend && pnpm format

format-check: ## Check formatting without changes
	cd backend && ../$(VENV_BIN)/ruff format --config pyproject.toml --check .
	cd frontend && pnpm format:check

typecheck: ## Run type checking
	cd frontend && pnpm typecheck

check: ## Run all checks (lint + format + typecheck)
	@echo "==> Linting..."
	$(MAKE) lint
	@echo "==> Checking format..."
	$(MAKE) format-check
	@echo "==> Type checking..."
	$(MAKE) typecheck
	@echo "==> All checks passed!"

# ============================================================
# Testing
# ============================================================

test: ## Run all tests
	cd backend && ../$(PYTHON) -m pytest tests/ -v
	cd frontend && pnpm test

test-backend: ## Run backend tests only
	cd backend && ../$(PYTHON) -m pytest tests/ -v

test-backend-cov: ## Run backend tests with coverage report
	cd backend && ../$(PYTHON) -m pytest tests/ --cov=. --cov-report=term-missing

test-frontend: ## Run all frontend tests
	cd frontend && pnpm test

# ============================================================
# Utilities
# ============================================================

env: ## Create .env from example
	cp .env.example .env
	@echo "Created .env — please fill in your API keys"

commit: ## AI-powered commit (uses Claude CLI)
	node scripts/ai-commit.mjs --all
