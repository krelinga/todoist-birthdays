"""Retrying Todoist client wrapper (design doc sections 5 & 6).

Every outbound Todoist call goes through `TodoistClient._call`, which
applies the shared retry policy (3 attempts, exponential backoff + jitter,
retrying only on network errors / 5xx / 429 -- a 429 honors `Retry-After`)
and records the metrics from design doc section 7. A 401/403 is its own
failure mode: it fails fast (no point retrying a bad token) and raises
TodoistAuthError instead of the generic TodoistAPIError, so it can be
alerted on distinctly from ordinary Todoist flakiness.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date
from typing import TypeVar

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter
from todoist_api_python.api import TodoistAPI

from . import metrics

T = TypeVar("T")

MAX_ATTEMPTS = 3
_BACKOFF = wait_exponential_jitter(initial=1, max=4)


class TodoistAuthError(Exception):
    """401/403 from Todoist -- expired or revoked API token. Not retried."""


class TodoistAPIError(Exception):
    """A Todoist API call failed after the retry policy was exhausted."""


class ProjectNotFoundError(Exception):
    """No Todoist project matches the configured name."""


def _status_code(exc: BaseException) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


def _retry_after_seconds(exc: BaseException | None) -> float | None:
    if not isinstance(exc, httpx.HTTPStatusError):
        return None
    header = exc.response.headers.get("Retry-After")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None  # HTTP-date form; fall back to the normal backoff schedule.


def _is_retryable(exc: BaseException) -> bool:
    status = _status_code(exc)
    if status is not None:
        return status == 429 or status >= 500
    return isinstance(exc, httpx.TransportError)


def _wait(retry_state) -> float:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    retry_after = _retry_after_seconds(exc)
    return retry_after if retry_after is not None else _BACKOFF(retry_state)


class TodoistClient:
    def __init__(self, api_token: str, *, client: TodoistAPI | None = None):
        self._api = client or TodoistAPI(api_token)

    def _call(self, operation: str, func: Callable[[], T]) -> T:
        def _attempt() -> T:
            start = time.monotonic()
            try:
                result = func()
            except Exception as exc:
                metrics.todoist_api_call_duration_seconds.labels(operation).observe(
                    time.monotonic() - start
                )
                status = _status_code(exc)
                if status in (401, 403):
                    metrics.todoist_api_requests_total.labels(operation, "failure").inc()
                    metrics.todoist_auth_failures_total.labels(operation).inc()
                    raise TodoistAuthError(
                        f"{operation}: authentication failed (status {status})"
                    ) from exc
                outcome = "retry" if _is_retryable(exc) else "failure"
                metrics.todoist_api_requests_total.labels(operation, outcome).inc()
                raise
            else:
                metrics.todoist_api_call_duration_seconds.labels(operation).observe(
                    time.monotonic() - start
                )
                metrics.todoist_api_requests_total.labels(operation, "success").inc()
                return result

        retrying = retry(
            reraise=True,
            stop=stop_after_attempt(MAX_ATTEMPTS),
            wait=_wait,
            retry=retry_if_exception(_is_retryable),
        )
        try:
            return retrying(_attempt)()
        except TodoistAuthError:
            raise
        except Exception as exc:
            metrics.todoist_api_failures_total.labels(operation).inc()
            raise TodoistAPIError(
                f"{operation} failed after {MAX_ATTEMPTS} attempts"
            ) from exc

    def find_project_id(self, project_name: str) -> str:
        def _fetch_all_projects() -> list:
            projects = []
            for page in self._api.get_projects():
                projects.extend(page)
            return projects

        for project in self._call("get_projects", _fetch_all_projects):
            if project.name == project_name:
                return project.id
        raise ProjectNotFoundError(f"No Todoist project named {project_name!r}")

    def create_task(
        self,
        *,
        content: str,
        project_id: str,
        due_date: date,
        deadline_date: date,
        priority: int,
    ) -> None:
        self._call(
            "create_task",
            lambda: self._api.add_task(
                content=content,
                project_id=project_id,
                due_date=due_date,
                deadline_date=deadline_date,
                priority=priority,
            ),
        )
