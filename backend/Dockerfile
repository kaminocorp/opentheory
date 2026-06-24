# OpenTheory backend (FastAPI) container image — built for Fly.io.
#
# Uses the official uv base image so the runtime matches local dev exactly (same uv, same
# Python 3.12, same lockfile resolution). Dependencies install in their own cached layer so
# rebuilds that only touch app source don't re-resolve the whole dependency tree.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# UV_COMPILE_BYTECODE: precompile .pyc at install time for faster cold starts.
# UV_LINK_MODE=copy: silence the hardlink warning when the cache and venv span filesystems.
# UV_PROJECT_ENVIRONMENT: install into a fixed, predictable venv path we add to PATH below.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    APP_ENV=production

WORKDIR /app

# 1) Install only dependencies first, from the locked manifest, without dev deps and without
#    the project itself — this layer is cached until pyproject.toml / uv.lock change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# 2) Copy the application source and finalize the environment.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8000

# `fastapi run` is the production entrypoint from fastapi[standard]: no autoreload, binds all
# interfaces. Fly routes to internal_port 8000 (see fly.toml). Migrations run separately via
# the fly.toml release_command, not here, so a failed migration never ships a broken release.
CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]
