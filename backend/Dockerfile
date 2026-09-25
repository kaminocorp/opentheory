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

# Optional Lean 4 for ``lean.prove`` Grade A. Off by default — CI and the slim
# Fly image stay Lean-free; a missing ``lean`` binary is honest undecided/unavailable
# and does not break other instruments.
# Enable:  docker build --build-arg INSTALL_LEAN=1
# Pin:     docker build --build-arg INSTALL_LEAN=1 --build-arg LEAN_TOOLCHAIN=leanprover/lean4:v4.14.0
# See docs/operations/deploy.md §Lean 4 (optional, 0.23.0 / 0.26.0).
ARG INSTALL_LEAN=0
ARG LEAN_TOOLCHAIN=leanprover/lean4:v4.14.0
RUN if [ "$INSTALL_LEAN" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git && \
      curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf \
        | sh -s -- -y --default-toolchain "$LEAN_TOOLCHAIN" && \
      rm -rf /var/lib/apt/lists/* ; \
    fi
ENV PATH="/root/.elan/bin:${PATH}"

# Optional Mathlib oleans + lake project for ``lean.prove`` mathlib=true.
# Requires INSTALL_LEAN=1. Off by default — CI stays green without it; a missing
# cache is honest undecided/mathlib_unavailable and never Grade A.
# Enable:  docker build --build-arg INSTALL_LEAN=1 --build-arg INSTALL_MATHLIB=1
# Pin:     --build-arg MATHLIB_REV=v4.14.0  (must match LEAN_TOOLCHAIN)
# The build fetches the Mathlib cache (several GB). Do not enable on the CI image.
# Redeclare Lean args so this layer can require INSTALL_LEAN=1.
ARG INSTALL_LEAN
ARG LEAN_TOOLCHAIN
ARG INSTALL_MATHLIB=0
ARG MATHLIB_REV=v4.14.0
ENV OPENTHEORY_MATHLIB_LAKE=/opt/opentheory/lean-mathlib \
    TOOLBENCH_MATHLIB_LAKE=/opt/opentheory/lean-mathlib
RUN if [ "$INSTALL_MATHLIB" = "1" ]; then \
      if [ "$INSTALL_LEAN" != "1" ]; then \
        echo "INSTALL_MATHLIB=1 requires INSTALL_LEAN=1" >&2; \
        exit 1; \
      fi; \
      mkdir -p /opt/opentheory/lean-mathlib && \
      cp -a /app/lean-mathlib/. /opt/opentheory/lean-mathlib/ && \
      printf '%s\n' "$LEAN_TOOLCHAIN" > /opt/opentheory/lean-mathlib/lean-toolchain && \
      sed -i "s/^rev = \".*\"/rev = \"${MATHLIB_REV}\"/" \
        /opt/opentheory/lean-mathlib/lakefile.toml && \
      cd /opt/opentheory/lean-mathlib && \
      lake update && \
      lake exe cache get && \
      lake build ; \
    fi

EXPOSE 8000

# `fastapi run` is the production entrypoint from fastapi[standard]: no autoreload, binds all
# interfaces. Fly routes to internal_port 8000 (see fly.toml). Migrations run separately via
# the fly.toml release_command, not here, so a failed migration never ships a broken release.
CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]
