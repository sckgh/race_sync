"""The PositionSource interface and the raw fix type sources emit.

A source produces *raw* observations — either a geodetic/plane fix (GPS) or a timing
event (loop crossing). The Fusion layer (``racesync.fusion``) turns raw fixes into the
unified Position Model by map-matching to the track and re-anchoring at crossings.

Keeping sources "dumb" (raw in, raw out) means a new hardware feed only has to speak its
own wire format; all the track/fusion logic lives in one place (specs/04 §4.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional, Protocol, runtime_checkable

from ..model import TimingEvent


@dataclass(frozen=True)
class RawFix:
    """A raw position observation from a position source, before map-matching.

    Either (lat, lon) or (x, y) must be supplied.

    Attributes:
        car_id: Identifier of the car this fix belongs to.
        t: Observation timestamp in seconds on the aligned clock.
        lat: Latitude in decimal degrees, if a geodetic fix is provided.
        lon: Longitude in decimal degrees, if a geodetic fix is provided.
        x: Plane x-coordinate, if a projected fix is provided.
        y: Plane y-coordinate, if a projected fix is provided.
        speed: Speed in m/s where the hardware provides it.
        heading: Heading in radians where the hardware provides it.
        quality: Fix type signalled as 0..1 (e.g. RTK-fixed vs float vs autonomous).
        meta: Arbitrary source-specific metadata.

    Raises:
        ValueError: If neither (lat, lon) nor (x, y) is supplied.
    """

    car_id: str
    t: float
    lat: Optional[float] = None
    lon: Optional[float] = None
    x: Optional[float] = None
    y: Optional[float] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    quality: float = 1.0
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        has_geo = self.lat is not None and self.lon is not None
        has_xy = self.x is not None and self.y is not None
        if not (has_geo or has_xy):
            raise ValueError("RawFix needs either (lat, lon) or (x, y)")


@dataclass
class SourceHealth:
    """Liveness/quality snapshot a source exposes to the Health Monitor (specs/09).

    Attributes:
        connected: Whether the source is currently producing data.
        last_packet_age: Seconds since the last packet was received.
        rate_hz: Observed packet rate in Hz.
        drop_rate: Fraction of expected packets that were dropped.
    """

    connected: bool = False
    last_packet_age: float = float("inf")
    rate_hz: float = 0.0
    drop_rate: float = 0.0


@runtime_checkable
class PositionSource(Protocol):
    """A pluggable real-world input.

    Implementations yield ``RawFix`` and/or ``TimingEvent`` objects from :meth:`stream`.
    ``stream`` may be finite (replay/file) or unbounded (live socket). The pull-based
    iterator keeps the core synchronous and trivially testable; a live transport can
    wrap a socket reader behind the same iterator.
    """

    name: str

    def stream(self) -> Iterator[RawFix | TimingEvent]:
        """Yield raw fixes and timing events as they arrive.

        Yields:
            ``RawFix`` and/or ``TimingEvent`` objects; the stream may be finite
            (replay/file) or unbounded (live socket).
        """
        ...

    def health(self) -> SourceHealth:
        ...
