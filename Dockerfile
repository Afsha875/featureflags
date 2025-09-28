FROM python:3.12-slim

# Install uv (pinned) for reproducible, fast dependency resolution.
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# Serve the on-disk-SQLite-backed app.
CMD ["uvicorn", "featureflags.app:app", "--host", "0.0.0.0", "--port", "8000"]
