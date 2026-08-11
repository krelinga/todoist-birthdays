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

RUN useradd --create-home --uid 1000 app \
    && DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src /app/src
COPY docker-entrypoint.sh /docker-entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Stays root so the entrypoint can chown the mounted state volume before
# dropping privileges to "app" (see docker-entrypoint.sh).
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "birthday_todoist.main"]
