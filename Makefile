# Wumpus Archiver — Makefile
# Convenience targets for development and production workflows.
# Requires: Python 3.12+, Node.js 18+, npm

.PHONY: help install dev serve build lint test clean

SHELL := /bin/bash
DB         ?= archive.db
HOST       ?= 127.0.0.1
PORT       ?= 8000
VITE_PORT  ?= 5173
ATT_DIR    ?= ./attachments

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ─── Setup ────────────────────────────────────────────────────────────────────

install: ## Install all dependencies (Python + Node)
	pip install -e ".[dev]"
	cd portal && npm install

install-py: ## Install Python dependencies only
	pip install -e ".[dev]"

install-js: ## Install Node/portal dependencies only
	cd portal && npm install

# ─── Development ──────────────────────────────────────────────────────────────

dev: ## Start dev environment (backend + frontend with hot-reload)
	wumpus-archiver dev $(DB) --port $(PORT) --frontend-port $(VITE_PORT) -a $(ATT_DIR)

dev-backend: ## Start only the backend with auto-reload
	uvicorn wumpus_archiver.api._dev_app:app --host $(HOST) --port $(PORT) --reload --reload-dir src

dev-frontend: ## Start only the Vite dev server
	cd portal && npm run dev -- --port $(VITE_PORT)

# ─── Production ───────────────────────────────────────────────────────────────

build: ## Build the SvelteKit portal for production
	cd portal && npm run build

serve: ## Start production server (API + built portal)
	wumpus-archiver serve $(DB) --host $(HOST) --port $(PORT) -a $(ATT_DIR)

serve-build: ## Build portal then start production server
	wumpus-archiver serve $(DB) --host $(HOST) --port $(PORT) -a $(ATT_DIR) --build-portal

# ─── Code Quality ─────────────────────────────────────────────────────────────

lint: ## Run all linters (ruff + mypy + svelte-check)
	ruff check src/ tests/
	mypy src/
	cd portal && npm run check

format: ## Auto-format code (ruff + black)
	ruff check --fix src/ tests/
	black src/ tests/

test: ## Run Python tests
	pytest

test-cov: ## Run tests with coverage report
	pytest --cov=src/wumpus_archiver --cov-report=term-missing

# ─── Data / Scraping ─────────────────────────────────────────────────────────

scrape: ## Scrape a guild (set GUILD_ID env var)
	wumpus-archiver scrape --guild-id $(GUILD_ID) -o $(DB) -v

download-images: ## Download all image attachments locally
	wumpus-archiver download $(DB) -o $(ATT_DIR) -v

# ─── Cleanup ──────────────────────────────────────────────────────────────────

clean: ## Remove build artifacts and caches
	rm -rf portal/build portal/.svelte-kit
	rm -rf src/wumpus_archiver/api/_dev_app.py
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
