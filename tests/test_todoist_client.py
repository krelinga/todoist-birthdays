from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from birthday_todoist import metrics, todoist_client
from birthday_todoist.todoist_client import (
    ProjectNotFoundError,
    TodoistAPIError,
    TodoistAuthError,
    TodoistClient,
)


def http_status_error(status_code: int, headers: dict | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.todoist.com/api/v1/tasks")
    response = httpx.Response(status_code, request=request, headers=headers or {})
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return exc
    raise AssertionError("expected a non-2xx status")


class FakeSDK:
    """Duck-types the bits of TodoistAPI our client calls."""

    def __init__(self, get_projects_pages=None, add_task_effects=None):
        self._get_projects_pages = get_projects_pages or []
        self._add_task_effects = list(add_task_effects or [])
        self.add_task_calls: list[dict] = []

    def get_projects(self):
        return iter(self._get_projects_pages)

    def add_task(self, **kwargs):
        self.add_task_calls.append(kwargs)
        effect = self._add_task_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    monkeypatch.setattr(todoist_client, "_wait", lambda retry_state: 0)


def counter_value(counter, *labels):
    return counter.labels(*labels)._value.get()


class TestFindProjectId:
    def test_finds_project_across_pages(self):
        projects_page_1 = [SimpleNamespace(id="1", name="Inbox")]
        projects_page_2 = [SimpleNamespace(id="2", name="Birthdays")]
        sdk = FakeSDK(get_projects_pages=[projects_page_1, projects_page_2])
        client = TodoistClient("token", client=sdk)

        assert client.find_project_id("Birthdays") == "2"

    def test_raises_when_not_found(self):
        sdk = FakeSDK(get_projects_pages=[[SimpleNamespace(id="1", name="Inbox")]])
        client = TodoistClient("token", client=sdk)

        with pytest.raises(ProjectNotFoundError):
            client.find_project_id("Birthdays")


class TestCreateTask:
    def test_success_calls_add_task_with_expected_kwargs(self):
        sdk = FakeSDK(add_task_effects=[SimpleNamespace(id="task-1")])
        client = TodoistClient("token", client=sdk)

        client.create_task(
            content="Wish Jane a happy birthday",
            project_id="proj-1",
            due_date=date(2026, 5, 7),
            deadline_date=date(2026, 5, 14),
            priority=3,
        )

        assert sdk.add_task_calls == [
            {
                "content": "Wish Jane a happy birthday",
                "project_id": "proj-1",
                "due_date": date(2026, 5, 7),
                "deadline_date": date(2026, 5, 14),
                "priority": 3,
            }
        ]

    def test_retries_transient_5xx_then_succeeds(self):
        sdk = FakeSDK(
            add_task_effects=[
                http_status_error(500),
                http_status_error(502),
                SimpleNamespace(id="task-1"),
            ]
        )
        client = TodoistClient("token", client=sdk)

        client.create_task(
            content="x", project_id="p", due_date=date(2026, 1, 1),
            deadline_date=date(2026, 1, 1), priority=1,
        )

        assert len(sdk.add_task_calls) == 3

    def test_retries_network_errors(self):
        sdk = FakeSDK(
            add_task_effects=[
                httpx.ConnectError("connection failed"),
                SimpleNamespace(id="task-1"),
            ]
        )
        client = TodoistClient("token", client=sdk)

        client.create_task(
            content="x", project_id="p", due_date=date(2026, 1, 1),
            deadline_date=date(2026, 1, 1), priority=1,
        )

        assert len(sdk.add_task_calls) == 2

    def test_exhausted_retries_raise_todoist_api_error(self):
        sdk = FakeSDK(
            add_task_effects=[http_status_error(500)] * 3,
        )
        client = TodoistClient("token", client=sdk)
        before = counter_value(metrics.todoist_api_failures_total, "create_task")

        with pytest.raises(TodoistAPIError):
            client.create_task(
                content="x", project_id="p", due_date=date(2026, 1, 1),
                deadline_date=date(2026, 1, 1), priority=1,
            )

        assert len(sdk.add_task_calls) == 3
        assert counter_value(metrics.todoist_api_failures_total, "create_task") == before + 1

    def test_max_attempts_is_configurable(self):
        sdk = FakeSDK(add_task_effects=[http_status_error(500)] * 2)
        client = TodoistClient("token", client=sdk, max_attempts=2)

        with pytest.raises(TodoistAPIError):
            client.create_task(
                content="x", project_id="p", due_date=date(2026, 1, 1),
                deadline_date=date(2026, 1, 1), priority=1,
            )

        assert len(sdk.add_task_calls) == 2

    def test_401_fails_fast_as_auth_error(self):
        sdk = FakeSDK(add_task_effects=[http_status_error(401)])
        client = TodoistClient("token", client=sdk)
        before = counter_value(metrics.todoist_auth_failures_total, "create_task")

        with pytest.raises(TodoistAuthError):
            client.create_task(
                content="x", project_id="p", due_date=date(2026, 1, 1),
                deadline_date=date(2026, 1, 1), priority=1,
            )

        assert len(sdk.add_task_calls) == 1
        assert counter_value(metrics.todoist_auth_failures_total, "create_task") == before + 1

    def test_403_fails_fast_as_auth_error(self):
        sdk = FakeSDK(add_task_effects=[http_status_error(403)])
        client = TodoistClient("token", client=sdk)

        with pytest.raises(TodoistAuthError):
            client.create_task(
                content="x", project_id="p", due_date=date(2026, 1, 1),
                deadline_date=date(2026, 1, 1), priority=1,
            )

        assert len(sdk.add_task_calls) == 1

    def test_non_retryable_4xx_fails_fast(self):
        sdk = FakeSDK(add_task_effects=[http_status_error(400)])
        client = TodoistClient("token", client=sdk)

        with pytest.raises(TodoistAPIError):
            client.create_task(
                content="x", project_id="p", due_date=date(2026, 1, 1),
                deadline_date=date(2026, 1, 1), priority=1,
            )

        assert len(sdk.add_task_calls) == 1

    def test_retry_after_header_used_as_wait(self, monkeypatch):
        sdk = FakeSDK(
            add_task_effects=[
                http_status_error(429, headers={"Retry-After": "2"}),
                SimpleNamespace(id="t"),
            ]
        )
        client = TodoistClient("token", client=sdk)
        waits = []
        monkeypatch.setattr(
            todoist_client, "_wait", lambda retry_state: waits.append(
                todoist_client._retry_after_seconds(retry_state.outcome.exception())
            ) or 0
        )

        client.create_task(
            content="x", project_id="p", due_date=date(2026, 1, 1),
            deadline_date=date(2026, 1, 1), priority=1,
        )

        assert waits == [2.0]
