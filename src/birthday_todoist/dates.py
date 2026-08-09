"""Birthday date math: next occurrence, days remaining, and age.

Feb 29 birthdays resolve to Feb 28 in non-leap target years (design doc
section 1) rather than skipping the year or rolling to Mar 1.
"""

from __future__ import annotations

import calendar
from datetime import date


def _birthday_in_year(month: int, day: int, year: int) -> date:
    if month == 2 and day == 29 and not calendar.isleap(year):
        day = 28
    return date(year, month, day)


def next_birthday(birthday: date, today: date) -> date:
    """The next occurrence of `birthday`'s month/day on or after `today`.

    Returns `today` itself when today is the birthday.
    """
    candidate = _birthday_in_year(birthday.month, birthday.day, today.year)
    if candidate < today:
        candidate = _birthday_in_year(birthday.month, birthday.day, today.year + 1)
    return candidate


def days_until(target: date, today: date) -> int:
    return (target - today).days


def age_on(birthday: date, on_date: date) -> int:
    """The age turned on `on_date`, given birth date `birthday`."""
    return on_date.year - birthday.year
