"""Dedupe state persisted across restarts (design doc section 3 & 6).

Maps a normalized person name to the year they were last reminded, so a
person is notified exactly once per birthday even across container
restarts or repeated ticks within the same notice window.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


class StateStore:
    def __init__(self, path: Path | str):
        self._path = Path(path)
        self._data: dict[str, int] = self._load()

    def _load(self) -> dict[str, int]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def already_sent(self, name: str, year: int) -> bool:
        return self._data.get(name) == year

    def mark_sent(self, name: str, year: int) -> None:
        """Record `name` as reminded for `year` and persist immediately.

        Writing right after each success (rather than batching until the end
        of a run) is what makes a mid-run crash safe: any person already
        marked sent won't be re-created on the next tick.
        """
        self._data[name] = year
        self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        with open(tmp_path, "w") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(self._path)
