# Birthday Reminder → Todoist: System Design

## 1. Requirements

**Functional**
- Config-driven people, keyed by name: `birthday` (date, required), `notice` (int, days, optional — defaults to `0`, meaning "the day of"), `priority` (optional, per person).
- Target Todoist project name is configurable via env var.
- Daily check: if today is `notice` days or fewer before a person's next birthday (and no reminder has fired yet this cycle), create a Todoist task. Using "or fewer" rather than "exactly" means a missed run (container down for a few days) still catches up on the next tick instead of silently skipping the reminder.
- Created task's due date = the day it's actually created (today, whichever day that ends up being within the notice window); deadline = the person's actual birthday.
- Created task's priority = the person's configured priority, or Todoist's default (P4) if unset.
- No duplicate tasks across restarts or repeated runs.
- Prometheus metrics exposed for monitoring (task creation, API failures, retries, run health).

**Non-functional**
- Single user / small list (tens to low hundreds of people) — this is a personal-scale job, not a distributed system.
- Runs as one Docker container, self-hostable (`docker run` / `docker compose up`, no external infra).
- Survives container restarts without re-firing already-sent reminders.
- Resilient to Todoist API flakiness: transient failures are retried before anything is surfaced as a metric/alert.
- Resilient to the container itself being down for a few days (e.g. host maintenance): the `<=` notice-window check catches up on the next run rather than requiring the check to land on the exact day.

**Constraints / assumptions**
- Todoist API token supplied via env var, one Todoist account/workspace.
- Tasks use both Todoist date fields: `due` = today (the day the task is created, so it lands on your list immediately) and `deadline` = the person's actual birthday (Todoist's dedicated deadline field, separate from `due`) — that's the literal read of "deadline of the person's birthday" plus scheduling it for creation day.
- Feb 29 birthdays: treated as **Feb 28** in non-leap years (confirmed).
- Timezone: one `TZ` for the whole system (when "today" ticks over).
- Metrics are exposed for scraping (pull model)

## 2. High-Level Design

```
+-------------------------------------------------+
|                 Docker Container                 |
|                                                   |
|   +-------------------+                          |
|   |  Scheduler loop    |  (in-process, e.g.       |
|   |  wakes daily at    |   APScheduler/cron-lite) |
|   |  configured TZ/time|                          |
|   +---------+---------+                          |
|             |                                     |
|             v                                     |
|   +-------------------+                          |
|   | Reminder Engine     |                          |
|   |  - load config.yaml |                          |
|   |  - compute next      |                          |
|   |    birthday/person   |                          |
|   |  - filter by "notice"|                          |
|   |  - dedupe vs state   |                          |
|   +---------+-----------+                          |
|             |                                     |
|             v                                     |
|   +-------------------+                          |
|   | Todoist REST Client |                          |
|   |  - resolve project   |                          |
|   |    name -> id (cached)|                        |
|   |  - create task w/     |                        |
|   |    due=today,         |                        |
|   |    deadline=birthday  |                        |
|   +---------+-----------+                          |
|             |                                     |
|             v                                     |
|   +-------------------+                          |
|   | State store          |  <-- persisted volume    |
|   | (person+year -> sent) |     /data/state.json     |
|   +---------------------+                          |
|             |                                     |
|             v                                     |
|   +-------------------+                          |
|   | Metrics registry    |  <-- scraped by your     |
|   | (/metrics HTTP)      |     Prometheus            |
|   +---------------------+                          |
+-------------------------------------------------+
         |                    |             |
         v                    v             v
  /config/config.yaml   Todoist Cloud API   Prometheus
      (RO)                                   (scrapes :9090/metrics)
```

**Volumes / env**
- `/config/config.yaml` — mounted read-only, hot-reloaded each tick (no rebuild to edit people).
- `/data/state.json` — mounted read-write, persists dedupe state across restarts.
- `TODOIST_API_TOKEN` — secret, via env or Docker secret.
- `TODOIST_PROJECT_NAME` — target Todoist project name (e.g. `Birthdays`).
- `TZ`, `RUN_AT` (e.g. `08:00`) — when the daily check fires.
- `METRICS_PORT` (default `9090`) — where `/metrics` is served.

## 3. Data Model

**config.yaml**
```yaml
people:
  "Jane Doe":
    birthday: "1990-05-14"   # full ISO date; year used for "turning N" in task text
    notice: 7
    priority: "p2"          # optional — p1 (urgent) .. p4 (default). Omit for P4.
  "John Smith":
    birthday: "1985-12-02"
    # notice omitted -> defaults to 0 (fires on the birthday itself)
    # priority omitted -> defaults to p4
```

**Priority mapping.** Todoist's UI labels (p1 = urgent … p4 = default/lowest) don't match the REST API's raw `priority` field, which runs the other direction (4 = urgent … 1 = default). The config uses the UI labels (`p1`–`p4`) since that's what you actually see in Todoist; the app translates to the API's numeric value at task-creation time:

| Config value | Meaning | API `priority` |
|---|---|---|
| `p1` | Urgent | `4` |
| `p2` | High | `3` |
| `p3` | Medium | `2` |
| `p4` / unset | Default | `1` |

**state.json** (or SQLite if you'd rather not hand-roll file locking)
```json
{
  "jane doe": 2026,
  "john smith": 2026
}
```
Key = the same name used as the config key (normalized), value = the year they were last notified. One entry per person, overwritten each year — so a person is reminded exactly once per birthday.

## 4. Core Logic (per daily tick)

1. Load `config.yaml` and `TODOIST_PROJECT_NAME`.
2. Resolve `TODOIST_PROJECT_NAME` → project ID (cache in memory / state file; re-resolve if a lookup ever misses). Wrapped in the retry logic below.
3. For each `name → person` entry in `people`:
   - Compute `next_birthday` = this year's birthday, or next year's if it's already passed. Feb 29 birthdays resolve to Feb 28 in non-leap target years.
   - `days_until = (next_birthday - today).days`
   - `notice = person.notice` if set, else `0`.
   - If `days_until <= notice` and `state.get(name) != next_birthday.year`:
     - Resolve priority: person's configured `priority`, mapped per the table above, else API value `1` (P4 default).
     - Create task via the retrying Todoist client: content per the fixed template below (selected by whether `notice` is `0` or `> 0`), `due: today`, `deadline: next_birthday`, `project_id`, `priority`.
     - On success, write `state[name] = next_birthday.year` and persist immediately (not batched) so a mid-run crash can't double-fire, and increment the `tasks_created_total` metric.
     - On exhausted-retry failure, leave state unset (so it's retried next tick) and increment `todoist_api_failures_total`.
4. Log a summary line per run (people checked, tasks created, errors) to stdout, and update the run-level metrics (last run timestamp, last run success/failure).

Handles the year-boundary edge case implicitly (e.g., a Jan 3 birthday with 10 days' notice, checked on Dec 24) because `next_birthday` rolls forward across Jan 1 automatically.

## 5. API Contract (internal — Todoist REST v2)

**Task content template (fixed, chosen by the resolved `notice` value — `0` if unset):**

| `notice` | Template |
|---|---|
| `0` (default) | `🎂 Wish {name} a happy birthday (turning {age})` |
| `> 0` | `🎂 Prepare for {name}'s birthday (turning {age})` |

where `{age} = next_birthday.year - birth_year`. The `notice == 0` case reads naturally because it can only ever fire on the birthday itself (see Core Logic — with `notice = 0`, `days_until <= notice` only becomes true when `days_until == 0`); the `notice > 0` case is a heads-up ahead of the day. No per-person override beyond this notice-driven choice.

- `GET /projects` → find project by name, cache ID. Re-fetch if project not found (renamed/deleted).
- `POST /tasks`:
  ```json
  {
    "content": "🎂 Prepare for Jane Doe's birthday (turning 36)",
    "project_id": "<resolved id>",
    "due": { "date": "2026-05-07" },
    "deadline": { "date": "2026-05-14" },
    "priority": 3
  }
  ```
  `due` is set to the creation date (today, i.e. `notice` days before the birthday) so the task lands on your list right away; `deadline` is the actual birthday, kept visually distinct from `due` in Todoist's UI. `priority` omitted entirely defaults to Todoist's own default (`1` / P4), so an unset config value can just be left off the payload rather than explicitly sent as `1`.

## 6. Reliability, Retries & Error Handling

Given Todoist's history of flakiness, retries are the first line of defense — metrics/alerting only kick in once retries are exhausted, so a single blip doesn't page anyone.

- Every outbound Todoist call (`GET /projects`, `POST /tasks`) goes through a shared retrying client: exponential backoff with jitter, e.g. 3 attempts at ~1s / 2s / 4s. Retries on network errors, timeouts, and 5xx; a 429 respects `Retry-After`; 4xx other than 429 (e.g. bad token, bad payload) fails fast — retrying a permanent error just delays the alert.
- Each individual attempt increments `todoist_api_requests_total{operation, outcome}`; only the *final* failure after retries are exhausted increments `todoist_api_failures_total{operation}` — that's the metric alerting should watch, not raw attempt counts.
- A 401/403 (expired or revoked token) is treated as its own failure mode: it fails fast (no point retrying a bad token) and increments a dedicated `todoist_auth_failures_total` counter instead of the generic failure counter, so an expired token pages differently than "Todoist is just being flaky."
- If a create call fails after retries, **don't** mark state as sent — it's retried again on the next scheduled tick (daily), not just within-run. Log loudly (stdout, so `docker logs` and log-based alerting both see it).
- Container restart policy: `unless-stopped`. Because state is on a mounted volume, a crash/restart mid-run can't cause a duplicate task (state is written right after each successful creation, not batched at the end).

## 7. Observability: Prometheus Metrics

The app serves `/metrics` on `METRICS_PORT` (default `9090`) via `prometheus_client`, for your existing Prometheus to scrape — no push gateway, no bundled Alertmanager.

| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `todoist_api_requests_total` | Counter | `operation` (`get_projects`/`create_task`), `outcome` (`success`/`retry`/`failure`) | Raw call volume, retry rate. |
| `todoist_api_failures_total` | Counter | `operation` | Calls that failed *after* retries were exhausted — the primary alert signal. |
| `todoist_auth_failures_total` | Counter | `operation` | 401/403 responses specifically (expired/revoked token) — fails fast, no retry, and alerts distinctly from generic flakiness. |
| `todoist_api_call_duration_seconds` | Histogram | `operation` | Latency, useful for spotting Todoist degrading before it starts failing outright. |
| `tasks_created_total` | Counter | — | Successful reminders created. |
| `reminder_run_last_success_timestamp` | Gauge | — | Unix time of the last fully-successful run — alert if this goes stale (e.g. no successful run in >26h) to catch the container being stuck/crash-looping, not just individual API failures. |
| `reminder_run_last_run_timestamp` | Gauge | — | Unix time of the last attempted run, success or not. |
| `people_checked_total` | Counter | — | Sanity metric — should track config size; a sudden drop flags a config-load problem. |

Example alerting rules you'd own in your own Prometheus/Alertmanager (not bundled here, just illustrative):
```
- alert: TodoistReminderAPIFailing
  expr: increase(todoist_api_failures_total[1d]) > 0
  for: 0m
- alert: TodoistReminderRunStale
  expr: time() - reminder_run_last_success_timestamp > 60 * 60 * 26
- alert: TodoistReminderAuthExpired
  expr: increase(todoist_auth_failures_total[1h]) > 0
  for: 0m
```

## 8. Tech Stack

- Python 3.12-slim base image.
- `todoist-api-python` (official SDK) or plain `requests` — SDK is less code, plain `requests` is less dependency risk. Either is fine at this scale; SDK recommended.
- `PyYAML` for config.
- `APScheduler` (or a 5-line `while True: sleep-until-next-RUN_AT` loop — genuinely equivalent at this scale, APScheduler mainly buys clean TZ handling).
- `prometheus_client` for the `/metrics` endpoint.
- `tenacity` (or hand-rolled) for the retry/backoff wrapper around Todoist calls.
- Single `Dockerfile` + `docker-compose.yml` for the self-host story:
  ```yaml
  services:
    birthday-reminder:
      build: .
      restart: unless-stopped
      environment:
        - TODOIST_API_TOKEN=${TODOIST_API_TOKEN}
        - TODOIST_PROJECT_NAME=Birthdays
        - TZ=America/Chicago
        - RUN_AT=08:00
        - METRICS_PORT=9090
      ports:
        - "9090:9090"   # for Prometheus to scrape
      volumes:
        - ./config.yaml:/config/config.yaml:ro
        - ./data:/data
  ```

## 9. Trade-off Analysis

| Decision | Chosen | Alternative | Why |
|---|---|---|---|
| Scheduling | In-process loop/APScheduler, long-running container | Host cron / k8s CronJob running a one-shot container | You asked for it to "run in a docker container" as the deployable unit — a long-running container with `docker run -d` is the simplest self-host story with zero external scheduling dependency. Cron-based is more "correct" for pure batch jobs but adds an external moving part. |
| Dedupe | Local state file (JSON/SQLite) on a mounted volume | Query Todoist for existing matching tasks each run | Querying Todoist to dedupe is fragile (string matching on content, breaks if you rename/complete the task manually) and costs extra API calls for no real benefit at this scale. |
| Birthday storage | Full ISO date (with birth year) | Month/day only | Costs nothing extra, lets the task text include "(turning 36)" as a nice-to-have, and avoids inventing a non-standard partial-date format. |
| Config delivery | Mounted YAML, re-read each tick | Baked into image | Editing the people list shouldn't require a rebuild/redeploy. |
| Metrics delivery | Pull (`/metrics` endpoint, scraped) | Push (Pushgateway) | Standard Prometheus pattern for a long-running service; a push model is really only needed for short-lived batch jobs, and this container runs continuously anyway. |
| Retry scope | Retry inside the Todoist client, alert only on exhaustion | Alert on every single API error | Todoist is known-flaky — alerting on every transient blip would be noisy and self-defeating. Retries absorb the noise; metrics/alerts reflect only failures that survived 3 attempts. |
