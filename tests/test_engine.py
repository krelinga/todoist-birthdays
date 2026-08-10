from datetime import date
from pathlib import Path

from birthday_todoist.engine import ReminderEngine, RunSummary
from birthday_todoist.state import StateStore


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


class FakeTodoistClient:
    def __init__(self, project_id="proj-1", find_project_error=None, create_task_error=None):
        self._project_id = project_id
        self._find_project_error = find_project_error
        self._create_task_error = create_task_error
        self.find_project_calls = 0
        self.created_tasks: list[dict] = []

    def find_project_id(self, project_name):
        self.find_project_calls += 1
        if self._find_project_error:
            raise self._find_project_error
        return self._project_id

    def create_task(self, **kwargs):
        if self._create_task_error:
            raise self._create_task_error
        self.created_tasks.append(kwargs)


def make_engine(tmp_path, config_text, client=None):
    config_path = write_config(tmp_path, config_text)
    state = StateStore(tmp_path / "state.json")
    client = client or FakeTodoistClient()
    engine = ReminderEngine(
        config_path=config_path,
        state=state,
        client=client,
        project_name="Birthdays",
    )
    return engine, state, client


class TestRunOnce:
    def test_creates_task_on_birthday_with_default_notice(self, tmp_path):
        engine, state, client = make_engine(
            tmp_path,
            """
            people:
              "Jane Doe":
                birthday: "1990-05-14"
            """,
        )

        summary = engine.run_once(date(2026, 5, 14))

        assert summary == RunSummary(people_checked=1, tasks_created=1, errors=0)
        assert client.created_tasks == [
            {
                "content": "\U0001f382 Wish Jane Doe a happy birthday (turning 36)",
                "project_id": "proj-1",
                "due_date": date(2026, 5, 14),
                "deadline_date": date(2026, 5, 14),
                "priority": 1,
            }
        ]
        assert state.already_sent("jane doe", 2026) is True

    def test_unknown_birth_year_omits_age_on_birthday(self, tmp_path):
        engine, _, client = make_engine(
            tmp_path,
            """
            people:
              "Jane Doe":
                birthday: "0000-05-14"
            """,
        )

        engine.run_once(date(2026, 5, 14))

        assert client.created_tasks[0]["content"] == "\U0001f382 Wish Jane Doe a happy birthday"

    def test_unknown_birth_year_omits_age_on_advance_notice(self, tmp_path):
        engine, _, client = make_engine(
            tmp_path,
            """
            people:
              "Jane Doe":
                birthday: "0000-05-14"
                notice: 7
            """,
        )

        engine.run_once(date(2026, 5, 7))

        assert client.created_tasks[0]["content"] == (
            "\U0001f382 Prepare for Jane Doe's birthday"
        )
        assert client.created_tasks[0]["deadline_date"] == date(2026, 5, 14)

    def test_advance_notice_uses_prepare_template_and_priority(self, tmp_path):
        engine, _, client = make_engine(
            tmp_path,
            """
            people:
              "Jane Doe":
                birthday: "1990-05-14"
                notice: 7
                priority: "p2"
            """,
        )

        engine.run_once(date(2026, 5, 7))

        assert client.created_tasks[0]["content"] == (
            "\U0001f382 Prepare for Jane Doe's birthday (turning 36)"
        )
        assert client.created_tasks[0]["priority"] == 3
        assert client.created_tasks[0]["deadline_date"] == date(2026, 5, 14)

    def test_outside_notice_window_is_skipped(self, tmp_path):
        engine, _, client = make_engine(
            tmp_path,
            """
            people:
              "Jane Doe":
                birthday: "1990-05-14"
                notice: 7
            """,
        )

        summary = engine.run_once(date(2026, 4, 1))

        assert summary.tasks_created == 0
        assert client.created_tasks == []

    def test_already_sent_this_year_is_skipped(self, tmp_path):
        engine, state, client = make_engine(
            tmp_path,
            """
            people:
              "Jane Doe":
                birthday: "1990-05-14"
            """,
        )
        state.mark_sent("jane doe", 2026)

        summary = engine.run_once(date(2026, 5, 14))

        assert summary.tasks_created == 0
        assert client.created_tasks == []

    def test_missed_run_still_fires_within_notice_window(self, tmp_path):
        # Container was down when the window opened (5 days out); the
        # "<=" check still fires when it comes back 3 days out instead.
        engine, state, client = make_engine(
            tmp_path,
            """
            people:
              "Jane Doe":
                birthday: "1990-05-14"
                notice: 5
            """,
        )

        summary = engine.run_once(date(2026, 5, 11))

        assert summary.tasks_created == 1
        assert state.already_sent("jane doe", 2026) is True

    def test_create_task_failure_does_not_mark_state_and_continues(self, tmp_path):
        client = FakeTodoistClient(create_task_error=RuntimeError("boom"))
        engine, state, client = make_engine(
            tmp_path,
            """
            people:
              "Jane Doe":
                birthday: "1990-05-14"
              "John Smith":
                birthday: "1990-05-14"
            """,
            client=client,
        )

        summary = engine.run_once(date(2026, 5, 14))

        assert summary.people_checked == 2
        assert summary.tasks_created == 0
        assert summary.errors == 2
        assert state.already_sent("jane doe", 2026) is False

    def test_project_resolution_is_cached_across_runs(self, tmp_path):
        engine, _, client = make_engine(
            tmp_path,
            """
            people: {}
            """,
        )

        engine.run_once(date(2026, 5, 14))
        engine.run_once(date(2026, 5, 15))

        assert client.find_project_calls == 1

    def test_project_not_found_is_caught_and_reported_as_error(self, tmp_path):
        client = FakeTodoistClient(find_project_error=RuntimeError("no such project"))
        engine, _, client = make_engine(
            tmp_path,
            """
            people:
              "Jane Doe":
                birthday: "1990-05-14"
            """,
            client=client,
        )

        summary = engine.run_once(date(2026, 5, 14))

        assert summary.errors == 1
        assert summary.people_checked == 0

    def test_project_resolution_retried_on_next_run_after_failure(self, tmp_path):
        client = FakeTodoistClient(find_project_error=RuntimeError("no such project"))
        engine, _, client = make_engine(tmp_path, "people: {}\n", client=client)

        engine.run_once(date(2026, 5, 14))
        client._find_project_error = None
        engine.run_once(date(2026, 5, 15))

        assert client.find_project_calls == 2
