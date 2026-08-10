from datetime import date
from pathlib import Path

import pytest

from birthday_todoist.config import ConfigError, load_config


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


def test_loads_people_with_defaults(tmp_path):
    path = write_config(
        tmp_path,
        """
        people:
          "John Smith":
            birthday: "1985-12-02"
        """,
    )
    people = load_config(path)
    person = people["john smith"]
    assert person.name == "John Smith"
    assert person.birthday == date(1985, 12, 2)
    assert person.birth_year == 1985
    assert person.notice == 0
    assert person.api_priority == 1


def test_loads_person_with_notice_and_priority(tmp_path):
    path = write_config(
        tmp_path,
        """
        people:
          "Jane Doe":
            birthday: "1990-05-14"
            notice: 7
            priority: "p2"
        """,
    )
    person = load_config(path)["jane doe"]
    assert person.notice == 7
    assert person.api_priority == 3


def test_key_is_normalized(tmp_path):
    path = write_config(
        tmp_path,
        """
        people:
          "  Jane Doe  ":
            birthday: "1990-05-14"
        """,
    )
    people = load_config(path)
    assert "jane doe" in people
    assert people["jane doe"].name == "  Jane Doe  "


def test_missing_birthday_raises(tmp_path):
    path = write_config(
        tmp_path,
        """
        people:
          "Jane Doe":
            notice: 7
        """,
    )
    with pytest.raises(ConfigError, match="birthday"):
        load_config(path)


def test_invalid_birthday_format_raises(tmp_path):
    path = write_config(
        tmp_path,
        """
        people:
          "Jane Doe":
            birthday: "not-a-date"
        """,
    )
    with pytest.raises(ConfigError, match="invalid birthday"):
        load_config(path)


def test_negative_notice_raises(tmp_path):
    path = write_config(
        tmp_path,
        """
        people:
          "Jane Doe":
            birthday: "1990-05-14"
            notice: -1
        """,
    )
    with pytest.raises(ConfigError, match="notice"):
        load_config(path)


def test_invalid_priority_raises(tmp_path):
    path = write_config(
        tmp_path,
        """
        people:
          "Jane Doe":
            birthday: "1990-05-14"
            priority: "urgent"
        """,
    )
    with pytest.raises(ConfigError, match="priority"):
        load_config(path)


def test_empty_config_returns_no_people(tmp_path):
    path = write_config(tmp_path, "people: {}\n")
    assert load_config(path) == {}


def test_unknown_birth_year_sets_birth_year_to_none(tmp_path):
    path = write_config(
        tmp_path,
        """
        people:
          "Jane Doe":
            birthday: "0000-05-14"
        """,
    )
    person = load_config(path)["jane doe"]
    assert person.birthday.month == 5
    assert person.birthday.day == 14
    assert person.birth_year is None


def test_unknown_birth_year_leap_day_parses(tmp_path):
    path = write_config(
        tmp_path,
        """
        people:
          "Jane Doe":
            birthday: "0000-02-29"
        """,
    )
    person = load_config(path)["jane doe"]
    assert person.birthday.month == 2
    assert person.birthday.day == 29
    assert person.birth_year is None


def test_unknown_birth_year_invalid_month_day_raises(tmp_path):
    path = write_config(
        tmp_path,
        """
        people:
          "Jane Doe":
            birthday: "0000-13-01"
        """,
    )
    with pytest.raises(ConfigError, match="invalid birthday"):
        load_config(path)
