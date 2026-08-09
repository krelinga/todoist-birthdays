"""Daily "sleep until next RUN_AT" loop (design doc sections 2 & 8).

A hand-rolled loop rather than APScheduler -- the design doc calls the two
genuinely equivalent at this scale, and this avoids an extra dependency
for a single daily wakeup. `zoneinfo` (stdlib) handles the TZ/DST math.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from datetime import time as time_of_day
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def next_run_at(now: datetime, run_at: time_of_day) -> datetime:
    """The next datetime (in `now`'s timezone) at or after `now` matching `run_at`."""
    candidate = datetime.combine(now.date(), run_at, tzinfo=now.tzinfo)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def run_forever(
    tick: Callable[[date], None],
    *,
    tz: ZoneInfo,
    run_at: time_of_day,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] | None = None,
) -> None:
    """Call `tick(today)` once daily at `run_at` in `tz`, forever."""
    clock = now or (lambda: datetime.now(tz))

    while True:
        target = next_run_at(clock(), run_at)
        wait_seconds = (target - clock()).total_seconds()
        if wait_seconds > 0:
            logger.info("Sleeping %.0fs until next run at %s", wait_seconds, target.isoformat())
            sleep(wait_seconds)
        tick(clock().date())
