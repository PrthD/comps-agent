# Backend container image. Build context is ./backend (see render.yaml).
# Stateless: the comps parquet is baked into the image; there is no database.
FROM python:3.11-slim

# uv from its official image (fast, reproducible installs from the lockfile).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first (cached layer) without the project, then with it.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# App code and the bundled read-only comps store. The .env is never copied;
# GEMINI_API_KEY and ALLOWED_ORIGINS come from the environment at runtime.
COPY app ./app
COPY data/kc_sales.parquet ./data/kc_sales.parquet
RUN uv sync --frozen --no-dev

# Render sets $PORT; default to 8000 locally. Shell form expands the variable.
CMD uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
