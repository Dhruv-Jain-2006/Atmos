FROM python:3.14-slim AS base

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Copy application code
COPY backend/ backend/
COPY workers/ workers/
COPY alembic.ini ./
COPY db/ db/

# Production startup script — reads PORT from Railway env
COPY start.py ./

# Install dependencies and project
RUN uv sync --frozen --no-dev

# PYTHONPATH ensures `backend.internetweather.api.app` resolves from /app
ENV PYTHONPATH=/app

EXPOSE 8000

# Use the startup script.  It reads $PORT from the Railway environment
# directly in Python, avoiding shell variable expansion issues.
CMD ["uv", "run", "python", "start.py"]
