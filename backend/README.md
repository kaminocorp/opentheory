# OpenTheory Backend

FastAPI backend for the OpenTheory research platform.

## Local Setup

```bash
uv sync
cp .env.example .env
uv run fastapi dev app/main.py
```

## Checks

```bash
uv run ruff check .
uv run pytest
```

## Migrations

```bash
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
```
