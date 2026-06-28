"""ReplaySource: play back recorded feeds for offline development and testing.

The whole point of the backbone (specs/09 §9.10) is that the system can be exercised end
to end off recorded events, without a live track or simulator. ReplaySource reads a JSON
Lines file where each line is one record:

    {"type": "fix",    "car_id": "12", "t": 1.0, "lat": -33.80, "lon": 150.87, "quality": 1.0}
    {"type": "fix",    "car_id": "12", "t": 1.1, "x": 12.0, "y": 4.0, "speed": 50.0}
    {"type": "timing", "kind": "lap_completed", "t": 95.3, "car_id": "12", "lap": 1}

Records are emitted in file order (which should be time order). This same format is what
a feed recorder writes from live sources, so a captured session replays verbatim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

from ..model import TimingEvent, TimingEventKind
from .base import RawFix, SourceHealth


class ReplaySource:
    """Replay recorded fixes/timing events from a JSON Lines file.

    Records are emitted in file order, which should also be time order.

    Args:
        path: Path to the JSON Lines file to replay.
        name: Optional source name; defaults to ``replay:<filename>``.
    """

    def __init__(self, path: str | Path, name: str | None = None):
        self.path = Path(path)
        self.name = name or f"replay:{self.path.name}"
        self._emitted = 0
        self._done = False

    @classmethod
    def from_records(cls, records: Iterable[dict], tmp_path: str | Path) -> "ReplaySource":
        """Write records to a JSONL file and return a source over it (test helper).

        Args:
            records: Iterable of record dicts to serialise, one per line.
            tmp_path: Destination path for the JSONL file.

        Returns:
            A ReplaySource reading the freshly written file.
        """
        p = Path(tmp_path)
        with p.open("w") as fh:
            for rec in records:
                fh.write(json.dumps(rec) + "\n")
        return cls(p)

    def stream(self) -> Iterator[RawFix | TimingEvent]:
        """Read the file and emit each record as an event.

        Blank lines and lines starting with ``#`` are skipped.

        Yields:
            A RawFix or TimingEvent for each decodable record, in file order.
        """
        with self.path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                rec = json.loads(line)
                event = _record_to_event(rec)
                if event is not None:
                    self._emitted += 1
                    yield event
        self._done = True

    def health(self) -> SourceHealth:
        """Report a liveness/quality snapshot for this source."""
        return SourceHealth(connected=not self._done, last_packet_age=0.0)


def _record_to_event(rec: dict) -> RawFix | TimingEvent | None:
    """Convert a parsed JSONL record into a RawFix or TimingEvent.

    Args:
        rec: The decoded record dict; its ``type`` selects the event kind.

    Returns:
        A RawFix for ``fix`` records, a TimingEvent for ``timing`` records, or None for
        any other type.
    """
    rtype = rec.get("type")
    if rtype == "fix":
        return RawFix(
            car_id=str(rec["car_id"]), t=float(rec["t"]),
            lat=rec.get("lat"), lon=rec.get("lon"),
            x=rec.get("x"), y=rec.get("y"),
            speed=rec.get("speed"), heading=rec.get("heading"),
            quality=float(rec.get("quality", 1.0)), meta=rec.get("meta", {}),
        )
    if rtype == "timing":
        return TimingEvent(
            kind=TimingEventKind(rec["kind"]), t=float(rec["t"]),
            car_id=(str(rec["car_id"]) if rec.get("car_id") is not None else None),
            lap=rec.get("lap"), sector=rec.get("sector"), value=rec.get("value"),
            meta=rec.get("meta", {}),
        )
    return None
