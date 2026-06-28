"""GPS position source: parse NMEA 0183 into RawFix.

Most GNSS/RTK receivers in the recommended hardware list (specs/11) emit NMEA 0183 over
serial/UDP/TCP, regardless of vendor. This source parses the two sentences that carry
what we need:

* ``GGA`` — position + fix quality (4 = RTK fixed, 5 = RTK float). Quality is mapped to
  the RawFix ``quality`` 0..1 so downstream code can prefer RTK-fixed data.
* ``RMC`` — position + speed-over-ground + course-over-ground (heading) + timestamp.

The parser (:class:`NmeaParser`) is transport-agnostic and pure, so it is unit-testable
against captured sentences. :class:`NmeaGpsSource` adapts it to the PositionSource
protocol over any line iterator (a file replay, a serial reader, or a UDP socket).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

from ..model import TimingEvent  # noqa: F401  (part of the source's yielded union)
from .base import PositionSource, RawFix, SourceHealth


# NMEA GGA fix-quality field -> our 0..1 quality and a label.
_GGA_QUALITY = {
    0: (0.0, "no-fix"),
    1: (0.4, "autonomous"),   # ~2.5 m typical
    2: (0.6, "dgps"),         # sub-metre
    4: (1.0, "rtk-fixed"),    # ~cm
    5: (0.8, "rtk-float"),    # ~dm
    6: (0.5, "dead-reckoning"),
}


def _nmea_checksum_ok(sentence: str) -> bool:
    """Validate an NMEA sentence's ``*HH`` checksum. Returns True if absent."""
    if "*" not in sentence:
        return True
    body, _, cks = sentence.partition("*")
    body = body[1:] if body.startswith("$") else body
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(cks[:2], 16)
    except ValueError:
        return False


def _dm_to_deg(value: str, hemi: str) -> Optional[float]:
    """Convert NMEA ddmm.mmmm + hemisphere to signed decimal degrees."""
    if not value:
        return None
    dot = value.find(".")
    deg_len = dot - 2 if dot >= 2 else len(value) - 2
    degrees = float(value[:deg_len])
    minutes = float(value[deg_len:])
    dec = degrees + minutes / 60.0
    if hemi in ("S", "W"):
        dec = -dec
    return dec


@dataclass
class NmeaParser:
    """Stateful NMEA parser for one receiver / car.

    Holds the latest known quality (from GGA) so an RMC sentence that lacks it still gets
    a sensible value. ``base_epoch`` (seconds) anchors NMEA's time-of-day to the aligned
    clock; if not given, wall-clock arrival time is used as ``t``.
    """

    car_id: str
    base_epoch: Optional[float] = None
    _last_quality: float = 1.0
    _last_quality_label: str = "unknown"

    def parse(self, line: str, arrival_t: Optional[float] = None) -> Optional[RawFix]:
        line = line.strip()
        if not line or not _nmea_checksum_ok(line):
            return None
        # Strip talker id: $GPGGA / $GNGGA / $GNRMC ... -> GGA / RMC
        head, _, _ = line.partition("*")
        fields = head.split(",")
        if not fields or len(fields[0]) < 6:
            return None
        kind = fields[0][-3:]
        if kind == "GGA":
            return self._parse_gga(fields, arrival_t)
        if kind == "RMC":
            return self._parse_rmc(fields, arrival_t)
        return None

    def _t(self, arrival_t: Optional[float]) -> float:
        if arrival_t is not None:
            return arrival_t
        return time.time() if self.base_epoch is None else self.base_epoch

    def _parse_gga(self, f, arrival_t) -> Optional[RawFix]:
        try:
            lat = _dm_to_deg(f[2], f[3])
            lon = _dm_to_deg(f[4], f[5])
            qual = int(f[6]) if f[6] else 0
        except (IndexError, ValueError):
            return None
        q, label = _GGA_QUALITY.get(qual, (0.3, "unknown"))
        self._last_quality, self._last_quality_label = q, label
        if lat is None or lon is None or qual == 0:
            return None
        return RawFix(
            car_id=self.car_id, t=self._t(arrival_t), lat=lat, lon=lon,
            quality=q, meta={"fix": label, "sentence": "GGA"},
        )

    def _parse_rmc(self, f, arrival_t) -> Optional[RawFix]:
        try:
            status = f[2]
            lat = _dm_to_deg(f[3], f[4])
            lon = _dm_to_deg(f[5], f[6])
            sog_knots = float(f[7]) if f[7] else None
            cog_deg = float(f[8]) if f[8] else None
        except (IndexError, ValueError):
            return None
        if status != "A" or lat is None or lon is None:
            return None
        speed = sog_knots * 0.514444 if sog_knots is not None else None  # knots -> m/s
        heading = math.radians(cog_deg) if cog_deg is not None else None
        return RawFix(
            car_id=self.car_id, t=self._t(arrival_t), lat=lat, lon=lon,
            speed=speed, heading=heading, quality=self._last_quality,
            meta={"fix": self._last_quality_label, "sentence": "RMC"},
        )


class NmeaGpsSource:
    """Adapt an iterable of NMEA lines (per car) to the PositionSource protocol.

    ``streams`` maps ``car_id -> iterable of NMEA text lines``. Lines are consumed
    round-robin so a multi-car replay interleaves naturally. For a live receiver, pass a
    single car's socket/serial line generator.
    """

    def __init__(self, streams: dict[str, Iterable[str]], base_epoch: Optional[float] = None):
        self.name = "nmea-gps"
        self._streams = {cid: iter(lines) for cid, lines in streams.items()}
        self._parsers = {cid: NmeaParser(cid, base_epoch=base_epoch) for cid in streams}
        self._count = 0
        self._exhausted = False

    def stream(self) -> Iterator[RawFix]:
        active = dict(self._streams)
        while active:
            for cid in list(active):
                try:
                    line = next(active[cid])
                except StopIteration:
                    del active[cid]
                    continue
                fix = self._parsers[cid].parse(line)
                if fix is not None:
                    self._count += 1
                    yield fix
        self._exhausted = True

    def health(self) -> SourceHealth:
        return SourceHealth(
            connected=not self._exhausted,
            last_packet_age=0.0 if self._count else float("inf"),
            rate_hz=0.0,
        )
