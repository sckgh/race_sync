"""Core data types shared across RaceSync components.

These mirror the internal event model in ``specs/03-system-architecture.md`` and the
Position Model in ``specs/04-data-feeds.md``. Everything here is plain stdlib so the
backbone has no third-party dependencies.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Optional


# --------------------------------------------------------------------------- #
# Position model (specs/04)
# --------------------------------------------------------------------------- #

class PositionSourceKind(str, enum.Enum):
    """Where a position estimate came from / how it was derived.

    Ordered loosely best->worst so consumers can prefer higher-quality sources.

    Attributes:
        GPS: Continuous GNSS (ideally RTK-fixed).
        FUSED: GPS re-anchored to a timing crossing.
        TIMING_INTERP: Interpolated between timing loops.
        DEAD_RECKONED: Extrapolated through a data gap.
    """

    GPS = "gps"                     # continuous GNSS (ideally RTK-fixed)
    FUSED = "fused"                 # GPS re-anchored to a timing crossing
    TIMING_INTERP = "timing_interp" # interpolated between timing loops
    DEAD_RECKONED = "dead_reckoned" # extrapolated through a data gap


@dataclass(frozen=True)
class LapDistance:
    """Position expressed in the track frame: which lap, and how far around it.

    ``total`` is a monotonic progress measure (``lap + s``) that is safe to compare/sort
    across cars and is the natural key for ordering and the timed finish (specs/06,
    specs/08).

    Attributes:
        lap: The lap number (>= 0).
        s: Fraction [0, 1) of the way around the lap, measured along the track
            centreline.
    """

    lap: int
    s: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.s < 1.0):
            raise ValueError(f"s must be in [0, 1), got {self.s}")
        if self.lap < 0:
            raise ValueError(f"lap must be >= 0, got {self.lap}")

    @property
    def total(self) -> float:
        return self.lap + self.s


@dataclass(frozen=True)
class PositionEstimate:
    """One estimate of where a car is, at time ``t`` (seconds, aligned clock).

    Attributes:
        car_id: Identifier of the car this estimate is for.
        t: Time of the estimate in seconds on the aligned clock.
        x: Track-plane east coordinate in metres (for injection).
        y: Track-plane north coordinate in metres (for injection).
        lap_distance: Along-track representation (for ordering/interpolation).
        source: How the estimate was derived.
        speed: Speed in m/s, measured (GPS) or estimated.
        heading: Heading in radians, 0 = +x axis, CCW positive.
        lat: Original geodetic latitude, when from GPS.
        lon: Original geodetic longitude, when from GPS.
        quality: A 0..1 confidence in the estimate.
        age: Staleness in seconds; lets consumers decay trust in stale estimates.
    """

    car_id: str
    t: float
    x: float
    y: float
    lap_distance: LapDistance
    source: PositionSourceKind
    speed: Optional[float] = None     # m/s, measured (GPS) or estimated
    heading: Optional[float] = None   # radians, 0 = +x axis, CCW positive
    lat: Optional[float] = None       # original geodetic, when from GPS
    lon: Optional[float] = None
    quality: float = 1.0
    age: float = 0.0

    def with_age(self, now: float) -> "PositionEstimate":
        """Return a copy with ``age`` recomputed and ``quality`` decayed for staleness.

        Quality halves roughly every second of staleness — a deliberately gentle decay
        so a brief gap does not crater confidence but a long one clearly does
        (specs/04 §4.3: plausible-and-stable beats precise-but-jumpy).

        Args:
            now: Current time in seconds on the aligned clock.

        Returns:
            A new estimate with ``age`` set to the staleness and ``quality`` decayed
            accordingly.
        """
        age = max(0.0, now - self.t)
        decay = 0.5 ** age
        return PositionEstimate(
            car_id=self.car_id, t=self.t, x=self.x, y=self.y,
            lap_distance=self.lap_distance, source=self.source,
            speed=self.speed, heading=self.heading, lat=self.lat, lon=self.lon,
            quality=self.quality * decay, age=age,
        )


# --------------------------------------------------------------------------- #
# Timing events (specs/04, specs/06)
# --------------------------------------------------------------------------- #

class TimingEventKind(str, enum.Enum):
    """Kinds of authoritative timing events.

    Attributes:
        PASSING: Transponder seen at a loop.
        SECTOR: Sector time recorded.
        LAP_COMPLETED: Car completed a lap.
        LEADER_CHANGED: The race leader changed.
        RACE_COMPLETED: Leader completed full race distance.
    """

    PASSING = "passing"                # transponder seen at a loop
    SECTOR = "sector"                  # sector time recorded
    LAP_COMPLETED = "lap_completed"    # car completed a lap
    LEADER_CHANGED = "leader_changed"  # the race leader changed
    RACE_COMPLETED = "race_completed"  # leader completed full race distance


@dataclass(frozen=True)
class TimingEvent:
    """An authoritative timing event (from MyLaps/official timing).

    RaceSync treats these as authoritative for laps, order and the finish trigger
    (specs/01 A2, specs/08).

    Attributes:
        kind: The kind of timing event.
        t: Time of the event in seconds.
        car_id: Car the event pertains to, when applicable.
        lap: Lap number the event pertains to.
        sector: Sector number the event pertains to, when applicable.
        value: Lap/sector time in seconds where relevant.
        meta: Additional event metadata.
    """

    kind: TimingEventKind
    t: float
    car_id: Optional[str] = None
    lap: Optional[int] = None
    sector: Optional[int] = None
    value: Optional[float] = None
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Shared race state (specs/06)
# --------------------------------------------------------------------------- #

class RaceState(str, enum.Enum):
    """The shared race state (specs/06).

    Attributes:
        PRE_RACE: Before the race has started.
        FORMATION: Formation lap in progress.
        GREEN: Racing under green-flag conditions.
        NEUTRALISED: Real Safety Car -> virtual Code 60.
        CHEQUERED: The race has finished.
    """

    PRE_RACE = "pre_race"
    FORMATION = "formation"
    GREEN = "green"
    NEUTRALISED = "neutralised"  # real Safety Car -> virtual Code 60
    CHEQUERED = "chequered"


@dataclass(frozen=True)
class StateTransition:
    """A change in shared race state, with provenance for the audit log (specs/06).

    Attributes:
        from_state: The state being left.
        to_state: The state being entered.
        t: Time of the transition in seconds.
        source: Origin of the change ("operator" | "timing" | "system").
        reason: Human-readable reason for the transition.
        meta: Additional transition metadata.
    """

    from_state: RaceState
    to_state: RaceState
    t: float
    source: str           # "operator" | "timing" | "system"
    reason: str = ""
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Small geo helpers (used by track.py and GPS sources)
# --------------------------------------------------------------------------- #

EARTH_RADIUS_M = 6_371_000.0


def geodetic_to_local(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """Equirectangular projection of (lat, lon) to local metres about a reference.

    Accurate to well under a metre over a few-km circuit, which is all the track frame
    needs (specs/04 §4.2).

    Args:
        lat: Latitude of the point in decimal degrees.
        lon: Longitude of the point in decimal degrees.
        ref_lat: Reference latitude in decimal degrees.
        ref_lon: Reference longitude in decimal degrees.

    Returns:
        The (east, north) offset from the reference in metres.
    """
    lat_r = math.radians(lat)
    ref_lat_r = math.radians(ref_lat)
    east = math.radians(lon - ref_lon) * math.cos((lat_r + ref_lat_r) / 2.0) * EARTH_RADIUS_M
    north = math.radians(lat - ref_lat) * EARTH_RADIUS_M
    return east, north


def local_to_geodetic(east: float, north: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """Inverse of :func:`geodetic_to_local`: local metres -> (lat, lon) decimal degrees.

    Args:
        east: East offset from the reference in metres.
        north: North offset from the reference in metres.
        ref_lat: Reference latitude in decimal degrees.
        ref_lon: Reference longitude in decimal degrees.

    Returns:
        The (lat, lon) of the point in decimal degrees.
    """
    lat = ref_lat + math.degrees(north / EARTH_RADIUS_M)
    mean_lat_r = (math.radians(lat) + math.radians(ref_lat)) / 2.0
    lon = ref_lon + math.degrees(east / (EARTH_RADIUS_M * math.cos(mean_lat_r)))
    return lat, lon
