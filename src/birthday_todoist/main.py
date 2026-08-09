"""Process entrypoint: env var wiring, metrics server, and the daily loop."""

from __future__ import annotations

import logging
import os
import sys
from datetime import time as time_of_day
from zoneinfo import ZoneInfo

from prometheus_client import start_http_server

from .engine import ReminderEngine
from .scheduler import run_forever
from .state import StateStore
from .todoist_client import TodoistClient

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "/config/config.yaml"
DEFAULT_STATE_PATH = "/data/state.json"
DEFAULT_TZ = "America/Chicago"
DEFAULT_RUN_AT = "08:00"
DEFAULT_METRICS_PORT = "9090"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def parse_run_at(value: str) -> time_of_day:
    try:
        hour_str, minute_str = value.split(":")
        return time_of_day(int(hour_str), int(minute_str))
    except ValueError as exc:
        raise SystemExit(f"RUN_AT must be HH:MM, got {value!r}") from exc


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    api_token = _required_env("TODOIST_API_TOKEN")
    project_name = _required_env("TODOIST_PROJECT_NAME")
    tz = ZoneInfo(os.environ.get("TZ", DEFAULT_TZ))
    run_at = parse_run_at(os.environ.get("RUN_AT", DEFAULT_RUN_AT))
    config_path = os.environ.get("CONFIG_PATH", DEFAULT_CONFIG_PATH)
    state_path = os.environ.get("STATE_PATH", DEFAULT_STATE_PATH)
    metrics_port = int(os.environ.get("METRICS_PORT", DEFAULT_METRICS_PORT))

    start_http_server(metrics_port)
    logger.info("Metrics server listening on :%d/metrics", metrics_port)

    engine = ReminderEngine(
        config_path=config_path,
        state=StateStore(state_path),
        client=TodoistClient(api_token),
        project_name=project_name,
    )

    logger.info("Starting daily reminder loop: RUN_AT=%s TZ=%s", run_at, tz)
    run_forever(engine.run_once, tz=tz, run_at=run_at)


if __name__ == "__main__":
    main()
