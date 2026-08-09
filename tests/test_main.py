from datetime import time as time_of_day

import pytest

from birthday_todoist import main as main_module
from birthday_todoist.engine import ReminderEngine
from birthday_todoist.main import parse_max_attempts, parse_run_at
from birthday_todoist.todoist_client import DEFAULT_MAX_ATTEMPTS


class TestParseRunAt:
    def test_parses_hh_mm(self):
        assert parse_run_at("08:00") == time_of_day(8, 0)
        assert parse_run_at("23:45") == time_of_day(23, 45)

    def test_invalid_format_raises_system_exit(self):
        with pytest.raises(SystemExit):
            parse_run_at("not-a-time")


class TestParseMaxAttempts:
    def test_parses_int(self):
        assert parse_max_attempts("5") == 5

    def test_non_integer_raises_system_exit(self):
        with pytest.raises(SystemExit):
            parse_max_attempts("not-a-number")

    def test_less_than_one_raises_system_exit(self):
        with pytest.raises(SystemExit):
            parse_max_attempts("0")


class TestMainWiring:
    def test_missing_required_env_var_exits(self, monkeypatch):
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        monkeypatch.delenv("TODOIST_PROJECT_NAME", raising=False)

        with pytest.raises(SystemExit):
            main_module.main()

    def test_wires_engine_and_starts_loop(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TODOIST_API_TOKEN", "token-123")
        monkeypatch.setenv("TODOIST_PROJECT_NAME", "Birthdays")
        monkeypatch.setenv("TZ", "America/Chicago")
        monkeypatch.setenv("RUN_AT", "09:30")
        monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.yaml"))
        monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
        monkeypatch.setenv("METRICS_PORT", "9191")

        started_ports = []
        monkeypatch.setattr(main_module, "start_http_server", started_ports.append)

        run_forever_calls = []

        def fake_run_forever(tick, *, tz, run_at, **kwargs):
            run_forever_calls.append((tick, tz, run_at))

        monkeypatch.setattr(main_module, "run_forever", fake_run_forever)

        main_module.main()

        assert started_ports == [9191]
        assert len(run_forever_calls) == 1
        tick, tz, run_at = run_forever_calls[0]
        assert run_at == time_of_day(9, 30)
        assert str(tz) == "America/Chicago"
        assert tick.__self__.__class__ is ReminderEngine
        assert tick.__self__._project_name == "Birthdays"
        assert tick.__self__._client._max_attempts == DEFAULT_MAX_ATTEMPTS

    def test_todoist_max_attempts_env_var_is_wired_through(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TODOIST_API_TOKEN", "token-123")
        monkeypatch.setenv("TODOIST_PROJECT_NAME", "Birthdays")
        monkeypatch.setenv("TODOIST_MAX_ATTEMPTS", "7")
        monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.yaml"))
        monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
        monkeypatch.setattr(main_module, "start_http_server", lambda port: None)

        run_forever_calls = []
        monkeypatch.setattr(
            main_module,
            "run_forever",
            lambda tick, *, tz, run_at, **kwargs: run_forever_calls.append(tick),
        )

        main_module.main()

        assert run_forever_calls[0].__self__._client._max_attempts == 7

    def test_defaults_project_name_to_inbox_when_unset(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TODOIST_API_TOKEN", "token-123")
        monkeypatch.delenv("TODOIST_PROJECT_NAME", raising=False)
        monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.yaml"))
        monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
        monkeypatch.setattr(main_module, "start_http_server", lambda port: None)

        run_forever_calls = []
        monkeypatch.setattr(
            main_module,
            "run_forever",
            lambda tick, *, tz, run_at, **kwargs: run_forever_calls.append(tick),
        )

        main_module.main()

        assert run_forever_calls[0].__self__._project_name == "Inbox"
