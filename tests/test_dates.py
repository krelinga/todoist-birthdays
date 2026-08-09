from datetime import date

from birthday_todoist.dates import age_on, days_until, next_birthday


class TestNextBirthday:
    def test_later_this_year(self):
        assert next_birthday(date(1990, 5, 14), date(2026, 1, 1)) == date(2026, 5, 14)

    def test_earlier_this_year_rolls_to_next_year(self):
        assert next_birthday(date(1990, 5, 14), date(2026, 6, 1)) == date(2027, 5, 14)

    def test_today_is_birthday(self):
        assert next_birthday(date(1990, 5, 14), date(2026, 5, 14)) == date(2026, 5, 14)

    def test_feb29_in_leap_target_year_stays_feb29(self):
        assert next_birthday(date(1992, 2, 29), date(2028, 1, 1)) == date(2028, 2, 29)

    def test_feb29_in_non_leap_target_year_becomes_feb28(self):
        assert next_birthday(date(1992, 2, 29), date(2026, 1, 1)) == date(2026, 2, 28)

    def test_feb29_after_feb28_in_non_leap_year_rolls_to_next_leap_year(self):
        # 2026 is not a leap year; asking after Feb 28 rolls to 2027 (also non-leap -> Feb 28).
        assert next_birthday(date(1992, 2, 29), date(2026, 3, 1)) == date(2027, 2, 28)

    def test_year_boundary_rollover(self):
        # Jan 3 birthday, checked on Dec 24 of the prior year.
        assert next_birthday(date(1985, 1, 3), date(2025, 12, 24)) == date(2026, 1, 3)


class TestDaysUntil:
    def test_positive_days(self):
        assert days_until(date(2026, 5, 14), date(2026, 5, 7)) == 7

    def test_zero_when_today(self):
        assert days_until(date(2026, 5, 14), date(2026, 5, 14)) == 0


class TestAgeOn:
    def test_age_matches_year_difference(self):
        assert age_on(date(1990, 5, 14), date(2026, 5, 14)) == 36
