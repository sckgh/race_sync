"""Pluggable position/timing sources (specs/04 §4.4).

Every input implements :class:`~racesync.sources.base.PositionSource` so the rest of the
system depends only on the unified Position Model — swapping or losing a source changes
fidelity, not correctness.
"""

from .base import PositionSource, RawFix
from .replay import ReplaySource
from .gps_nmea import NmeaParser, NmeaGpsSource
from .mylaps import MyLapsX2Source

__all__ = [
    "PositionSource",
    "RawFix",
    "ReplaySource",
    "NmeaParser",
    "NmeaGpsSource",
    "MyLapsX2Source",
]
