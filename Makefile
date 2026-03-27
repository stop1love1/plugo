# ============================================
# Plugo — Development Commands
# ============================================
#
# All dependencies are installed locally:
#   - Python: .venv/ (project-local virtualenv)
#   - Node.js: node_modules/ (per package)
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
# Setup & Install (one-time)
# ============================================================

setup: ## Full project setup (venv + all deps + env file)
	@echo "==> Creating Python virtual environment..."
	python -m venv .venv
	@echo "==> Installing Python dependencies..."
	$(PIP) install -r backend/requirements-dev.txt
	@echo "==> Installing Node.js dependencies..."
	npm install
	cd dashboard && npm install
	cd widget && npm install
	@echo "==> Creating .env file..."
	@test -f .env || cp .env.example .env
	@echo ""
	@echo "  Setup complete! Edit .env with your API keys, then run: make dev"
	@echo ""

install: ## Install all dependencies (assumes venv exists)
	$(PIP) install -r backend/requirements.txt
	npm install
	cd dashboard && npm install
	cd widget && npm install

install-dev: ## Install all dependencies including dev tools
	$(PIP) install -r backend/requirements-dev.txt
	npm install
	cd dashboard && npm install
	cd widget && npm install
	$(VENV_BIN)/pre-commit install

# ============================================================
# Development (single commands)
# ============================================================

dev: ## Start all services (backend + dashboard + widget)
	npx concurrently -n backend,dashboard,widget -c blue,green,yellow \
		"cd backend && ../$(PYTHON) -m uvicorn main:app --reload --host 0.0.0.0 --port 8000" \
		"cd dashboard && npm run dev" \
		"cd widget && npm run dev"

dev-backend: ## Start backend only
	cd backend && ../$(PYTHON) -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

dev-dashboard: ## Start dashboard only
	cd dashboard && npm run dev

dev-widget: ## Start widget dev server
	cd widget && npm run dev

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
	cd widget && npm run build
	cd dashboard && npm run build

build-widget: ## Build widget only
	cd widget && npm run build

# ============================================================
# Code Quality
# ============================================================

lint: ## Run all linters
	cd backend && ../$(VENV_BIN)/ruff check .
	cd dashboard && npm run lint
	cd widget && npm run lint

lint-fix: ## Run all linters with auto-fix
	cd backend && ../$(VENV_BIN)/ruff check --fix .
	cd dashboard && npm run lint:fix
	cd widget && npm run lint:fix

format: ## Format all code
	cd backend && ../$(VENV_BIN)/ruff format .
	cd dashboard && npm run format
	cd widget && npm run format

format-check: ## Check formatting without changes
	cd backend && ../$(VENV_BIN)/ruff format --check .
	cd dashboard && npm run format:check
	cd widget && npm run format:check

typecheck: ## Run type checking
	cd dashboard && npm run typecheck
	cd widget && npm run typecheck

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
	cd dashboard && npm run test
	cd widget && npm run test

test-backend: ## Run backend tests only
	cd backend && ../$(PYTHON) -m pytest tests/ -v

test-backend-cov: ## Run backend tests with coverage report
	cd backend && ../$(PYTHON) -m pytest tests/ --cov=. --cov-report=term-missing

test-dashboard: ## Run dashboard tests only
	cd dashboard && npm run test

test-widget: ## Run widget tests only
	cd widget && npm run test

# ============================================================
# Utilities
# ============================================================

env: ## Create .env from example
	cp .env.example .env
	@echo "Created .env — please fill in your API keys"
