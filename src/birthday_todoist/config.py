"""Loading and validating config.yaml (design doc section 3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

# Todoist's UI priority labels (p1 = urgent .. p4 = default) map onto the REST
# API's numeric `priority` field in reverse (4 = urgent .. 1 = default).
PRIORITY_MAP: dict[str, int] = {
    "p1": 4,
    "p2": 3,
    "p3": 2,
    "p4": 1,
}

DEFAULT_API_PRIORITY = PRIORITY_MAP["p4"]

# A "0000" year means the birth year is unknown -- date.fromisoformat can't
# represent year 0, so month/day are parsed against this placeholder (which
# must be a leap year, so an unknown-year Feb 29 birthday still parses) and
# Person.birth_year is set to None instead.
_UNKNOWN_BIRTH_YEAR = "0000"
_PLACEHOLDER_YEAR = 4


class ConfigError(ValueError):
    """config.yaml is missing a required field or has an invalid value."""


@dataclass(frozen=True)
class Person:
    name: str
    birthday: date  # month/day is the real birthday; year is a placeholder when birth_year is None
    birth_year: int | None
    notice: int = 0
    api_priority: int = DEFAULT_API_PRIORITY


def _parse_person(name: str, raw: Any) -> Person:
    if not isinstance(raw, dict) or "birthday" not in raw:
        raise ConfigError(f"{name!r}: 'birthday' is required")

    raw_birthday = str(raw["birthday"])
    unknown_birth_year = raw_birthday.startswith(f"{_UNKNOWN_BIRTH_YEAR}-")
    parseable_birthday = (
        f"{_PLACEHOLDER_YEAR:04d}{raw_birthday[4:]}" if unknown_birth_year else raw_birthday
    )
    try:
        birthday = date.fromisoformat(parseable_birthday)
    except ValueError as exc:
        raise ConfigError(f"{name!r}: invalid birthday {raw['birthday']!r}") from exc
    birth_year = None if unknown_birth_year else birthday.year

    notice = raw.get("notice", 0)
    if not isinstance(notice, int) or isinstance(notice, bool) or notice < 0:
        raise ConfigError(f"{name!r}: 'notice' must be a non-negative integer")

    priority = raw.get("priority")
    if priority is None:
        api_priority = DEFAULT_API_PRIORITY
    else:
        try:
            api_priority = PRIORITY_MAP[str(priority).strip().lower()]
        except KeyError as exc:
            raise ConfigError(
                f"{name!r}: 'priority' must be one of {sorted(PRIORITY_MAP)}"
            ) from exc

    return Person(
        name=name,
        birthday=birthday,
        birth_year=birth_year,
        notice=notice,
        api_priority=api_priority,
    )


def load_config(path: Path | str) -> dict[str, Person]:
    """Load and validate config.yaml, keyed by normalized (trimmed, lowercased) name.

    The normalized key is also what's stored in state.json, so dedupe lookups
    and config lookups always agree.
    """
    raw = yaml.safe_load(Path(path).read_text()) or {}
    people = raw.get("people") or {}

    result: dict[str, Person] = {}
    for name, person_raw in people.items():
        person = _parse_person(name, person_raw)
        result[name.strip().lower()] = person
    return result
