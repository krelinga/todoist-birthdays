"""Per-tick reminder logic (design doc section 4)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import metrics
from .config import Person, load_config
from .dates import age_on, days_until, next_birthday
from .state import StateStore
from .todoist_client import TodoistClient

logger = logging.getLogger(__name__)

_NO_NOTICE_TEMPLATE = "\U0001f382 Wish {name} a happy birthday (turning {age})"
_NO_NOTICE_TEMPLATE_NO_AGE = "\U0001f382 Wish {name} a happy birthday"
_ADVANCE_NOTICE_TEMPLATE = "\U0001f382 Prepare for {name}'s birthday (turning {age})"
_ADVANCE_NOTICE_TEMPLATE_NO_AGE = "\U0001f382 Prepare for {name}'s birthday"


def _task_content(person: Person, age: int | None) -> str:
    is_no_notice = person.notice == 0
    if age is None:
        template = _NO_NOTICE_TEMPLATE_NO_AGE if is_no_notice else _ADVANCE_NOTICE_TEMPLATE_NO_AGE
        return template.format(name=person.name)
    template = _NO_NOTICE_TEMPLATE if is_no_notice else _ADVANCE_NOTICE_TEMPLATE
    return template.format(name=person.name, age=age)


@dataclass
class RunSummary:
    people_checked: int = 0
    tasks_created: int = 0
    errors: int = 0


class ReminderEngine:
    """Wires config, dates, state, and the Todoist client together for one daily tick."""

    def __init__(
        self,
        *,
        config_path: Path | str,
        state: StateStore,
        client: TodoistClient,
        project_name: str,
    ):
        self._config_path = config_path
        self._state = state
        self._client = client
        self._project_name = project_name
        self._project_id: str | None = None

    def run_once(self, today: date) -> RunSummary:
        summary = RunSummary()
        metrics.reminder_run_last_run_timestamp.set_to_current_time()
        try:
            people = load_config(self._config_path)
            project_id = self._resolve_project_id()
            for name, person in people.items():
                summary.people_checked += 1
                metrics.people_checked_total.inc()
                self._maybe_remind(name, person, today, project_id, summary)
        except Exception:
            logger.exception("Reminder run failed")
            summary.errors += 1

        logger.info("Reminder run complete: %s", summary)
        if summary.errors == 0:
            metrics.reminder_run_last_success_timestamp.set_to_current_time()
        return summary

    def _resolve_project_id(self) -> str:
        # Cached for the life of the process; a failed lookup leaves the
        # cache unset so the next tick re-resolves (e.g. after a rename).
        if self._project_id is None:
            self._project_id = self._client.find_project_id(self._project_name)
        return self._project_id

    def _maybe_remind(
        self, name: str, person: Person, today: date, project_id: str, summary: RunSummary
    ) -> None:
        target = next_birthday(person.birthday, today)
        if days_until(target, today) > person.notice:
            return
        if self._state.already_sent(name, target.year):
            return

        age = age_on(person.birthday, target) if person.birth_year is not None else None
        content = _task_content(person, age)
        try:
            self._client.create_task(
                content=content,
                project_id=project_id,
                due_date=today,
                deadline_date=target,
                priority=person.api_priority,
            )
        except Exception:
            logger.exception("Failed to create birthday task for %s", person.name)
            summary.errors += 1
            return

        self._state.mark_sent(name, target.year)
        metrics.tasks_created_total.inc()
        summary.tasks_created += 1
