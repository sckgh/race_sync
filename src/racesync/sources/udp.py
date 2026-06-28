"""UDP position telemetry source — the car -> RaceSync uplink (specs/12).

Cars send position **up** to RaceSync Feed Ingestion over UDP (freshness beats
completeness, so UDP not TCP). Two payload forms are accepted, both decoded to ``RawFix``:

* **Raw NMEA** — the car forwards ``$..GGA/RMC`` sentences; parsed by ``NmeaParser`` (a
  ``car_id`` must be associated with the listener, since NMEA carries no id).
* **Compact RaceSync telemetry packet** — a small JSON record that carries the car id and
  fix quality explicitly (preferred for bandwidth and routing).

The decoder is pure and unit-testable. ``UdpTelemetrySource`` adapts it to the
``PositionSource`` protocol over either a test iterable of payloads or a real UDP socket,
mirroring the injectable pattern used by the other sources/adapters.
"""

from __future__ import annotations

import json
import socket
from typing import Iterable, Iterator, Optional

from ..model import TimingEvent  # noqa: F401 (part of the yielded union for symmetry)
from .base import RawFix, SourceHealth
from .gps_nmea import NmeaParser


def encode_telemetry_packet(fix: RawFix, seq: int = 0) -> bytes:
    """Encode a RawFix as the compact uplink packet a car would send (car side)."""
    payload = {"v": 1, "seq": seq, "car": fix.car_id, "t": round(fix.t, 4)}
    for src, dst in (("lat", "lat"), ("lon", "lon"), ("x", "x"), ("y", "y")):
        v = getattr(fix, src)
        if v is not None:
            payload[dst] = v
    if fix.speed is not None:
        payload["spd"] = round(fix.speed, 3)
    if fix.heading is not None:
        payload["hdg"] = round(fix.heading, 4)
    payload["q"] = round(fix.quality, 3)
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def decode_telemetry_packet(data: bytes,
                            nmea_parser: Optional[NmeaParser] = None) -> Optional[RawFix]:
    """Decode an uplink payload (compact JSON packet or raw NMEA) into a RawFix."""
    text = data.decode("utf-8", errors="ignore").strip()
    if not text:
        return None
    if text[0] == "{":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return None
        if "car" not in obj or "t" not in obj:
            return None
        return RawFix(
            car_id=str(obj["car"]), t=float(obj["t"]),
            lat=obj.get("lat"), lon=obj.get("lon"),
            x=obj.get("x"), y=obj.get("y"),
            speed=obj.get("spd"), heading=obj.get("hdg"),
            quality=float(obj.get("q", 1.0)),
            meta={"seq": obj.get("seq")},
        )
    if text[0] == "$" and nmea_parser is not None:
        return nmea_parser.parse(text)
    return None


class UdpTelemetrySource:
    """Position uplink source over UDP (or a test iterable of payloads).

    Construct with ``packets=`` (an iterable of ``bytes``) for tests/replay, or use
    :meth:`listen` to bind a real socket. ``nmea_car_id`` associates a car id with raw NMEA
    payloads on this listener (ignored for JSON packets, which carry their own id).
    """

    def __init__(self, packets: Optional[Iterable[bytes]] = None,
                 nmea_car_id: Optional[str] = None, name: str = "udp-telemetry"):
        self.name = name
        self._packets = packets
        self._sock: Optional[socket.socket] = None
        self._nmea = NmeaParser(nmea_car_id) if nmea_car_id else None
        self._count = 0
        self._done = False

    @classmethod
    def listen(cls, host: str = "0.0.0.0", port: int = 9101,
               nmea_car_id: Optional[str] = None, bufsize: int = 2048) -> "UdpTelemetrySource":
        src = cls(nmea_car_id=nmea_car_id)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, port))
        src._sock = sock
        src._bufsize = bufsize
        return src

    def _iter_payloads(self) -> Iterator[bytes]:
        if self._packets is not None:
            yield from self._packets
            return
        assert self._sock is not None, "no packets and no socket"
        while True:
            data, _addr = self._sock.recvfrom(getattr(self, "_bufsize", 2048))
            yield data

    def stream(self) -> Iterator[RawFix]:
        for data in self._iter_payloads():
            fix = decode_telemetry_packet(data, self._nmea)
            if fix is not None:
                self._count += 1
                yield fix
        self._done = True

    def health(self) -> SourceHealth:
        return SourceHealth(connected=not self._done,
                            last_packet_age=0.0 if self._count else float("inf"))
