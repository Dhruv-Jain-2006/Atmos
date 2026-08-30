FROM python:3.14-slim AS base

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Copy application code (needed for uv sync --no-install-project fails without it)
COPY backend/ backend/
COPY workers/ workers/
COPY alembic.ini ./
COPY db/ db/

# Install dependencies and project
RUN uv sync --frozen --no-dev

# PYTHONPATH ensures `backend.internetweather.api.app` resolves from /app
ENV PYTHONPATH=/app

EXPOSE 8000

# Railway provides PORT env var; default to 8000
CMD ["sh", "-c", "uv run uvicorn backend.internetweather.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
