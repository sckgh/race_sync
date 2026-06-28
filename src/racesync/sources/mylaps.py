"""MyLaps X2 timing source (interface + stub).

The live X2 data-feed protocol and our access to it are still to be confirmed
(specs/02 TBC-2). This module therefore provides:

* a clean ``MyLapsX2Source`` shaped like the real adapter, so the rest of the system can
  be built and tested against it now, and
* a simple in-memory feeder (``feed_passing`` / ``feed_lap``) used by tests and by the
  replay tooling to simulate transponder crossings and lap completions.

When the real X2 feed details land, only the connection/parse internals of this class
change; the emitted ``TimingEvent`` stream — which is what RaceSync depends on — stays
the same.
"""

from __future__ import annotations

from collections import deque
from typing import Iterator, Optional

from ..model import TimingEvent, TimingEventKind
from .base import SourceHealth


class MyLapsX2Source:
    """Authoritative timing source emitting ``TimingEvent`` (laps, sectors, leader).

    In this stub, events are pushed in via :meth:`feed_passing` / :meth:`feed_lap` /
    :meth:`feed_race_completed` and drained by :meth:`stream`. A live implementation
    would instead connect to the X2 server and translate its messages into the same
    events.

    Args:
        name: Source name used by the Health Monitor.
    """

    def __init__(self, name: str = "mylaps-x2"):
        self.name = name
        self._queue: deque[TimingEvent] = deque()
        self._closed = False
        self._seen = 0

    # -- feed API (test/replay; replaced by a live connection later) -------- #

    def feed_passing(self, car_id: str, t: float, loop: Optional[str] = None) -> None:
        """Queue a transponder passing (loop crossing) event.

        Args:
            car_id: Identifier of the car that crossed the loop.
            t: Crossing timestamp in seconds.
            loop: Optional loop/decoder identifier recorded in the event metadata.
        """
        self._queue.append(TimingEvent(
            kind=TimingEventKind.PASSING, t=t, car_id=str(car_id),
            meta={"loop": loop} if loop else {},
        ))

    def feed_lap(self, car_id: str, t: float, lap: int, lap_time: Optional[float] = None) -> None:
        """Queue a lap-completed event.

        Args:
            car_id: Identifier of the car that completed the lap.
            t: Lap completion timestamp in seconds.
            lap: The completed lap number.
            lap_time: Optional lap time in seconds, recorded as the event value.
        """
        self._queue.append(TimingEvent(
            kind=TimingEventKind.LAP_COMPLETED, t=t, car_id=str(car_id),
            lap=lap, value=lap_time,
        ))

    def feed_leader_changed(self, car_id: str, t: float, lap: int) -> None:
        """Queue a leader-changed event.

        Args:
            car_id: Identifier of the car that became the new leader.
            t: Timestamp of the leader change in seconds.
            lap: Lap number at which the change occurred.
        """
        self._queue.append(TimingEvent(
            kind=TimingEventKind.LEADER_CHANGED, t=t, car_id=str(car_id), lap=lap,
        ))

    def feed_race_completed(self, car_id: str, t: float, lap: int) -> None:
        """Queue a race-completed event (the leader has run the full race distance).

        This is the timed-finish trigger.

        Args:
            car_id: Identifier of the leading car that completed the race distance.
            t: Timestamp of the trigger in seconds.
            lap: Lap number on which the race distance was completed.
        """
        self._queue.append(TimingEvent(
            kind=TimingEventKind.RACE_COMPLETED, t=t, car_id=str(car_id), lap=lap,
        ))

    def close(self) -> None:
        """Mark the source as closed."""
        self._closed = True

    # -- PositionSource protocol ------------------------------------------- #

    def stream(self) -> Iterator[TimingEvent]:
        """Drain the queued timing events.

        Yields:
            Queued TimingEvent objects in FIFO order until the queue is empty.
        """
        while self._queue:
            self._seen += 1
            yield self._queue.popleft()

    def health(self) -> SourceHealth:
        """Report a liveness/quality snapshot for this source."""
        return SourceHealth(
            connected=not self._closed,
            last_packet_age=0.0 if self._seen else float("inf"),
        )
