"""FeedRecorder: capture raw source events to the JSONL replay format.

This is the inverse of :class:`~racesync.sources.replay.ReplaySource`. Recording the raw
inputs a live session produced — then replaying that file — gives **capture/replay
parity**: the system behaves identically offline, which is the foundation of the
replay-based test rig and the audit trail (specs/09 §9.10, specs/03 §3.3).

Records are written in the same schema ReplaySource reads, so ``record`` then ``stream``
round-trips exactly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .model import TimingEvent
from .sources.base import RawFix


def to_record(event: RawFix | TimingEvent) -> Optional[dict]:
    """Convert a raw event to a JSONL record dict (None keys omitted for tidiness)."""
    if isinstance(event, RawFix):
        rec = {"type": "fix", "car_id": event.car_id, "t": event.t}
        for k in ("lat", "lon", "x", "y", "speed", "heading"):
            v = getattr(event, k)
            if v is not None:
                rec[k] = v
        rec["quality"] = event.quality
        if event.meta:
            rec["meta"] = event.meta
        return rec
    if isinstance(event, TimingEvent):
        rec = {"type": "timing", "kind": event.kind.value, "t": event.t}
        for k in ("car_id", "lap", "sector", "value"):
            v = getattr(event, k)
            if v is not None:
                rec[k] = v
        if event.meta:
            rec["meta"] = event.meta
        return rec
    return None


class FeedRecorder:
    """Append raw events to a JSONL file. Usable as a context manager.

        with FeedRecorder("session.jsonl") as rec:
            pipeline = Pipeline(fusion, recorder=rec, ...)
            pipeline.run(sources)
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.count = 0
        self._fh = None

    def __enter__(self) -> "FeedRecorder":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> None:
        if self._fh is None:
            self._fh = self.path.open("w")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def record(self, event: RawFix | TimingEvent) -> None:
        rec = to_record(event)
        if rec is None:
            return
        if self._fh is None:
            self.open()
        self._fh.write(json.dumps(rec) + "\n")
        self.count += 1
