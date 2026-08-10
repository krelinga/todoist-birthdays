# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project goals and design

The design doc for this project is located at `docs/design/birthday-todoist-reminder-design.md`.

The goal of this project is to build a system to automatically generate birthday reminders in todoist.

## Project status

The design has been implemented per the design doc. `src/birthday_todoist/`
contains the full application (config loading, birthday date math, state/dedupe,
the retrying Todoist client, the reminder engine, the daily scheduler loop, and
the `main.py` entrypoint), with a matching test in `tests/` for every module.
A Dockerfile and docker-compose.yml provide the self-host story.

This has been validated end-to-end against a real Todoist account, through the
actual built Docker image: project resolution, task creation (`due` +
`deadline` + `priority`), state persistence, and dedupe on a repeat run all
confirmed working. One finding from that test: Todoist's **Deadlines**
feature (the `deadline_date` field this app sets on every task) requires a
**Pro or Business** Todoist plan — on a Free-plan account, task creation
fails with an HTTP 403 that our client correctly classifies as an auth-type
failure (fails fast, no retry). There's no plan-detection or fallback in the
app; it assumes the account can use deadlines.

## Development environment

The devcontainer is based on `mcr.microsoft.com/devcontainers/base:noble` with:
- Node.js (LTS) via the `ghcr.io/devcontainers/features/node:2` feature
- Python 3.12 via the `ghcr.io/devcontainers/features/python:1` feature
- Docker-in-Docker via the `ghcr.io/devcontainers/features/docker-in-docker:2` feature
- The Claude Code CLI feature (`ghcr.io/anthropics/devcontainer-features/claude-code:1.0`)
- `postCreateCommand` installs [uv](https://docs.astral.sh/uv/) (`pip install --user uv`),
  this project's package/dependency manager

## Tech stack

- Python 3.12, managed with `uv` (`pyproject.toml` + `uv.lock`).
- `todoist-api-python` (v4, httpx-based) for the Todoist API — see
  `src/birthday_todoist/todoist_client.py` for the retry/error-classification
  wrapper around it (401/403 fail fast, 5xx/429 retry with backoff+jitter,
  429 honors `Retry-After`).
- `PyYAML` for `config.yaml`, `prometheus_client` for `/metrics`, `tenacity`
  for retries.
- `pytest` + `ruff` for tests/lint (dev dependency group).

## Build, lint, and test commands

Run from the repo root:
```sh
uv sync --dev                      # install/update dependencies into .venv
uv run pytest                      # run the full test suite
uv run pytest tests/test_dates.py  # run one test file
uv run pytest tests/test_dates.py::TestNextBirthday::test_today_is_birthday  # run one test
uv run ruff check src tests        # lint
```

## Running locally / authentication

1. `cp config.example.yaml config.yaml` and fill in real people/birthdays
   (gitignored — never commit this file).
2. `cp .env.example .env` and set `TODOIST_API_TOKEN` (from Todoist's
   integration settings). `TODOIST_PROJECT_NAME` is optional and defaults to
   `Inbox` if unset.
3. `docker compose up --build` — mounts `config.yaml` read-only and persists
   dedupe state to `./data/state.json`.

For a quick one-off run without Docker: `uv run python -m birthday_todoist.main`
with the same env vars exported and `CONFIG_PATH`/`STATE_PATH` pointed at local
files (they default to `/config/config.yaml` and `/data/state.json`, which only
exist inside the container).

## CI / image publishing

`.github/workflows/docker-publish.yml` is manual-only (`workflow_dispatch`,
triggered from the Actions tab) — it builds the Dockerfile and pushes to
`ghcr.io/krelinga/todoist-birthdays`, tagged with the input tag (default
`latest`) and the commit SHA. Auth uses the automatic `GITHUB_TOKEN`
(`permissions: packages: write` in the workflow) — no secrets to create.
There is no push/PR-triggered CI (no lint/test workflow) yet.

## Next steps for future instances

- Consider adding a push/PR-triggered lint+test workflow (only the manual
  image-publish workflow exists so far).
- The account used for testing requires a Pro/Business Todoist plan because
  of the deadline requirement above — if the target account is Free-tier,
  either drop `deadline_date` from `create_task` or make it configurable.
- Always confirm with the user before pushing local commits, even though the
  repo is currently in sync with `origin/main`.
