"""Fusion: turn raw source observations into the unified Position Model.

Responsibilities (specs/04 §4.1–4.3):

* **map-match** every GPS/plane fix onto the track frame to get along-track ``s``;
* **count laps** authoritatively from timing ``lap_completed`` events, so ``s`` plus the
  lap count gives a monotonic progress measure for ordering and the timed finish;
* **re-anchor** GPS to a known position at each loop crossing (the crossing pins ``s`` to
  a loop, correcting drift) — emitted as ``FUSED`` quality;
* **dead-reckon** through short gaps and **degrade** through long ones, never teleporting
  an injected car.

Fusion is pull-based and synchronous: feed it raw events, get back ``PositionEstimate``s.
A runner wires it to the bus; tests drive it directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .model import (
    LapDistance,
    PositionEstimate,
    PositionSourceKind,
    TimingEvent,
    TimingEventKind,
    geodetic_to_local,
)
from .sources.base import RawFix
from .track import TrackFrame

# Beyond this staleness (seconds) we stop dead-reckoning and mark a car as degraded
# rather than inventing motion (specs/04 §4.3; the regs even tolerate a 3-lap dropout).
DEAD_RECKON_MAX_AGE = 5.0


@dataclass
class _CarState:
    laps_completed: int = 0
    last: Optional[PositionEstimate] = None
    last_loop_s: Optional[float] = None
    anchored_until: float = float("-inf")  # while >= fix time, fixes count as FUSED


class Fusion:
    """Fuses raw fixes + timing into unified position estimates for each car."""

    def __init__(self, track: TrackFrame, anchor_window: float = 2.0):
        self.track = track
        self._cars: dict[str, _CarState] = {}
        self._anchor_window = anchor_window  # seconds a crossing keeps fixes "FUSED"

    def _car(self, car_id: str) -> _CarState:
        return self._cars.setdefault(car_id, _CarState())

    # -- ingestion ---------------------------------------------------------- #

    def on_timing_event(self, ev: TimingEvent) -> None:
        """Update lap counting / re-anchoring from authoritative timing."""
        if ev.car_id is None:
            return
        car = self._car(ev.car_id)
        if ev.kind == TimingEventKind.LAP_COMPLETED and ev.lap is not None:
            car.laps_completed = ev.lap
            car.anchored_until = ev.t + self._anchor_window
            car.last_loop_s = 0.0  # lap line crossing pins s to the start/finish loop
        elif ev.kind == TimingEventKind.PASSING:
            car.anchored_until = ev.t + self._anchor_window

    def on_fix(self, fix: RawFix) -> PositionEstimate:
        """Map-match a raw fix and produce a unified PositionEstimate."""
        car = self._car(fix.car_id)
        # Resolve plane coordinates.
        if fix.x is not None and fix.y is not None:
            x, y = fix.x, fix.y
            proj = self.track.project(x, y)
        else:
            x, y = geodetic_to_local(fix.lat, fix.lon, self.track.ref[0], self.track.ref[1])
            proj = self.track.project(x, y)

        s = proj.s
        # Lap-rollover safety net if timing is silent: a big backward jump in s while
        # near the start/finish line implies we crossed the line.
        if car.last is not None:
            prev_s = car.last.lap_distance.s
            if prev_s > 0.9 and s < 0.1 and car.anchored_until < fix.t:
                car.laps_completed += 1

        source = (
            PositionSourceKind.FUSED
            if fix.t <= car.anchored_until
            else PositionSourceKind.GPS
        )
        est = PositionEstimate(
            car_id=fix.car_id, t=fix.t, x=x, y=y,
            lap_distance=LapDistance(lap=car.laps_completed, s=s),
            source=source, speed=fix.speed,
            heading=fix.heading if fix.heading is not None else proj.heading,
            lat=fix.lat, lon=fix.lon, quality=fix.quality,
        )
        car.last = est
        car.last_loop_s = car.last_loop_s
        return est

    # -- dead reckoning / degradation -------------------------------------- #

    def extrapolate(self, car_id: str, now: float) -> Optional[PositionEstimate]:
        """Best estimate of a car's position at ``now`` when no fresh fix exists.

        Advances the last estimate along the track by ``speed * dt`` for short gaps
        (DEAD_RECKONED); returns a quality-decayed copy without inventing motion for long
        gaps; returns ``None`` if we have nothing to go on.
        """
        car = self._cars.get(car_id)
        if car is None or car.last is None:
            return None
        last = car.last
        dt = now - last.t
        if dt <= 0:
            return last
        if dt > DEAD_RECKON_MAX_AGE or not last.speed:
            # Too stale (or no speed): degrade in place, don't fabricate movement.
            return last.with_age(now)

        # Advance along the centreline by distance travelled.
        advance_m = last.speed * dt
        ds = advance_m / self.track.length
        new_total = last.lap_distance.total + ds
        new_lap = int(new_total)
        new_s = new_total - new_lap
        x, y, heading = self.track.point_at(new_s)
        est = PositionEstimate(
            car_id=car_id, t=now, x=x, y=y,
            lap_distance=LapDistance(lap=new_lap, s=new_s),
            source=PositionSourceKind.DEAD_RECKONED, speed=last.speed,
            heading=heading, quality=last.quality * (0.5 ** dt),
        )
        return est

    # -- queries ------------------------------------------------------------ #

    def latest(self, car_id: str) -> Optional[PositionEstimate]:
        car = self._cars.get(car_id)
        return car.last if car else None

    def order(self) -> list[str]:
        """Current car order by track progress (most-advanced first)."""
        live = [(cid, c.last) for cid, c in self._cars.items() if c.last is not None]
        live.sort(key=lambda kv: kv[1].lap_distance.total, reverse=True)
        return [cid for cid, _ in live]
