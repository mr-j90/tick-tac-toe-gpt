FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /srv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_SYNC=1 \
    PYTHONUNBUFFERED=1

# Dependencies first: this layer is cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

# Non-root. Nothing here needs write access at runtime — the store is in memory.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8000

# No secrets in the image or in build args: OPENAI_API_KEY arrives at runtime
# from `fly secrets set`, and get_client() returns None without it.
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
