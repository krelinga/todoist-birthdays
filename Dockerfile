FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Install dependencies first so they're cached separately from app code.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY src ./src
RUN uv sync --locked --no-dev

FROM python:3.12-slim

RUN useradd --create-home --uid 1000 app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src /app/src

ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
USER app

CMD ["python", "-m", "birthday_todoist.main"]
