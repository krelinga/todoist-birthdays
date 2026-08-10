# todoist-birthdays

Automatically creates birthday reminder tasks in [Todoist](https://todoist.com),
driven by a simple YAML file of names and birthdays. Runs as a single
long-lived Docker container: once a day it checks who's about to have (or is
having) a birthday and creates a task if one hasn't already been sent for
that person this year.

- Each task's **due date** is the day it's created; its **deadline** is the
  person's actual birthday, so the two stay visually distinct in Todoist.
- A person is reminded at most once per birthday, even across container
  restarts — dedupe state is persisted to a mounted volume.
- Feb 29 birthdays are treated as Feb 28 in non-leap years.
- Todoist API calls are retried with backoff on transient failures; an
  expired/revoked token fails fast instead of retrying.
- Prometheus metrics are served on `/metrics` for monitoring.

See [`docs/design/birthday-todoist-reminder-design.md`](docs/design/birthday-todoist-reminder-design.md)
for the full design.

> **Todoist plan note:** every task sets a deadline, and Todoist's
> [Deadlines feature](https://www.todoist.com/help/articles/introduction-to-deadlines-in-todoist-uMqbSLM6U)
> requires a **Pro or Business** plan. On a Free-plan account, task creation
> fails with an HTTP 403.

## Quick start

```sh
cp config.example.yaml config.yaml   # fill in real people/birthdays
cp .env.example .env                 # fill in your Todoist API token
docker compose up --build
```

`config.yaml` and `.env` are gitignored — never commit them.

## Config file: `config.yaml`

Mounted read-only at `/config/config.yaml` and re-read on every tick (no
rebuild needed to add/change people). Keyed by name:

```yaml
people:
  "Jane Doe":
    birthday: "1990-05-14" # full ISO date; the year is used for "turning N" in the task text
    notice: 7 # days of advance notice; omit to default to 0 (fires on the birthday itself)
    priority: "p2" # optional: p1 (urgent) .. p4 (default). Omit for p4.
  "John Smith":
    birthday: "1985-12-02"
    # notice omitted -> defaults to 0
    # priority omitted -> defaults to p4
```

The name is normalized (trimmed, lowercased) as the dedupe key, so renaming
a person in this file starts their dedupe history over.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TODOIST_API_TOKEN` | **Yes** | — | Your Todoist API token (Settings → Integrations → Developer). |
| `TODOIST_PROJECT_NAME` | No | `Inbox` | Name of the Todoist project reminders are created in. Must already exist. |
| `TZ` | No | `America/Chicago` | Timezone used to decide when "today" ticks over and when `RUN_AT` fires. |
| `RUN_AT` | No | `08:00` | Local time (`HH:MM`, 24h) the daily check runs. |
| `METRICS_PORT` | No | `9090` | Port the `/metrics` HTTP endpoint listens on. |
| `TODOIST_MAX_ATTEMPTS` | No | `3` | Retry attempts per Todoist API call before giving up. |
| `CONFIG_PATH` | No | `/config/config.yaml` | Path to the config file. Only useful if not using the standard mount. |
| `STATE_PATH` | No | `/data/state.json` | Path to the dedupe state file. Only useful if not using the standard mount. |

## Volumes

| Container path | Mode | Purpose |
|---|---|---|
| `/config/config.yaml` | read-only | The people/birthdays config, described above. |
| `/data` | read-write | Persists `state.json` (dedupe state) across restarts. |

## Running without Docker Compose

```sh
docker build -t todoist-birthdays .
docker run -d \
  --restart unless-stopped \
  --env-file .env \
  -p 9090:9090 \
  -v "$(pwd)/config.yaml:/config/config.yaml:ro" \
  -v "$(pwd)/data:/data" \
  todoist-birthdays
```

## Monitoring

Metrics are served at `http://<host>:<METRICS_PORT>/metrics` for scraping by
your own Prometheus — there's no bundled Prometheus or Alertmanager. See
section 7 of the design doc for the full metric list and example alert rules
(API failures, auth failures, stale runs).

## Building/publishing the image

`.github/workflows/docker-publish.yml` is a manual (`workflow_dispatch`)
GitHub Actions workflow that builds and pushes to
`ghcr.io/krelinga/todoist-birthdays`. Trigger it from the repo's Actions tab.

The image is tagged from the `version` field in `pyproject.toml` (must be
`MAJOR.MINOR.PATCH`) — a run with `version = "1.4.2"` pushes `:1`, `:1.4`,
and `:1.4.2`, plus `:latest` and the commit SHA every time.

### Cutting a release

1. Bump `version` in `pyproject.toml` (e.g. `"0.1.0"` → `"0.2.0"`) and commit it.
2. Push/merge that commit to `main`.
3. Go to the repo's Actions tab → "Build and Push Docker Image" → Run workflow.
4. The workflow reads the version straight off `main`'s `pyproject.toml` at
   run time — there's no separate version input, so make sure the bump is
   merged first.

## Development

See [`CLAUDE.md`](CLAUDE.md) for the tech stack, and build/lint/test commands.
