# OpenTheory — common dev tasks. Run from the repo root: `make <target>`.
# Backend uses uv (commands run in backend/.venv with locked deps); frontend uses npm.
# Bare `make` (or `make help`) lists every target.

.DEFAULT_GOAL := help
.PHONY: help dev migrate migration downgrade test lint sync fe fe-install

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}'

# --- Backend (FastAPI + uv) ---
dev: ## Run the backend dev server (http://localhost:8000)
	cd backend && uv run fastapi dev app/main.py

migrate: ## Apply Alembic migrations to head
	cd backend && uv run alembic upgrade head

migration: ## Autogenerate a migration:  make migration m="add widget table"
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

downgrade: ## Roll back one migration
	cd backend && uv run alembic downgrade -1

test: ## Run backend tests (DB-backed ones skip without TEST_DATABASE_URL)
	cd backend && uv run pytest

lint: ## Lint the backend (ruff)
	cd backend && uv run ruff check .

sync: ## Install/sync backend deps from uv.lock
	cd backend && uv sync

# --- Frontend (Next.js + npm) ---
fe: ## Run the frontend dev server (http://localhost:3000)
	cd frontend && npm run dev

fe-install: ## Install frontend deps
	cd frontend && npm install
