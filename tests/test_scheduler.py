from datetime import date, datetime
from datetime import time as time_of_day
from zoneinfo import ZoneInfo

import pytest

from birthday_todoist.scheduler import next_run_at, run_forever

TZ = ZoneInfo("America/Chicago")


class TestNextRunAt:
    def test_run_at_later_today(self):
        now = datetime(2026, 5, 14, 6, 0, tzinfo=TZ)
        assert next_run_at(now, time_of_day(8, 0)) == datetime(2026, 5, 14, 8, 0, tzinfo=TZ)

    def test_run_at_already_passed_today_rolls_to_tomorrow(self):
        now = datetime(2026, 5, 14, 9, 0, tzinfo=TZ)
        assert next_run_at(now, time_of_day(8, 0)) == datetime(2026, 5, 15, 8, 0, tzinfo=TZ)

    def test_exact_run_at_moment_rolls_to_tomorrow(self):
        # If we're woken exactly on the mark, treat this tick as already
        # handled and wait for the next one rather than double-firing.
        now = datetime(2026, 5, 14, 8, 0, tzinfo=TZ)
        assert next_run_at(now, time_of_day(8, 0)) == datetime(2026, 5, 15, 8, 0, tzinfo=TZ)


class StopLoop(Exception):
    pass


class TestRunForever:
    def test_ticks_once_per_day_in_order(self):
        clock_values = iter(
            [
                datetime(2026, 5, 14, 6, 0, tzinfo=TZ),  # loop 1: compute target
                datetime(2026, 5, 14, 6, 0, tzinfo=TZ),  # loop 1: wait_seconds calc
                datetime(2026, 5, 14, 8, 0, tzinfo=TZ),  # loop 1: post-sleep tick date
                datetime(2026, 5, 14, 8, 0, tzinfo=TZ),  # loop 2: compute target
                datetime(2026, 5, 14, 8, 0, tzinfo=TZ),  # loop 2: wait_seconds calc
                datetime(2026, 5, 15, 8, 0, tzinfo=TZ),  # loop 2: post-sleep tick date
            ]
        )
        ticked_dates = []
        sleep_calls = []

        def fake_now():
            return next(clock_values)

        def fake_sleep(seconds):
            sleep_calls.append(seconds)

        def tick(today: date):
            ticked_dates.append(today)
            if len(ticked_dates) == 2:
                raise StopLoop

        with pytest.raises(StopLoop):
            run_forever(tick, tz=TZ, run_at=time_of_day(8, 0), sleep=fake_sleep, now=fake_now)

        assert ticked_dates == [date(2026, 5, 14), date(2026, 5, 15)]
        assert sleep_calls == [pytest.approx(2 * 3600), pytest.approx(24 * 3600)]

    def test_does_not_sleep_when_target_already_passed_by_second_clock_read(self):
        # now() is read twice per iteration (target calc, then wait_seconds
        # calc); if time drifted past the target in between, skip sleeping
        # instead of passing a negative duration to sleep().
        clock_values = iter(
            [
                datetime(2026, 5, 14, 6, 0, tzinfo=TZ),  # target calc -> 8:00 target
                datetime(2026, 5, 14, 9, 0, tzinfo=TZ),  # wait_seconds calc: already past
                datetime(2026, 5, 14, 9, 0, tzinfo=TZ),  # tick date
            ]
        )
        sleep_calls = []

        def tick(today: date):
            raise StopLoop

        with pytest.raises(StopLoop):
            run_forever(
                tick,
                tz=TZ,
                run_at=time_of_day(8, 0),
                sleep=lambda s: sleep_calls.append(s),
                now=lambda: next(clock_values),
            )

        assert sleep_calls == []
