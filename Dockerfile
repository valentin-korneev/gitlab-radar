FROM ghcr.io/astral-sh/uv:python3.15-trixie-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY web ./web
RUN uv sync --locked --no-dev

EXPOSE 8000

CMD ["sh", "-c", "uv run --no-sync tortoise migrate && exec uv run --no-sync gitlab-radar"]
