"""NMEA 0183 test-data generator: simulate a field of cars emitting GPS sentences.

Produces realistic ``$GxGGA`` + ``$GxRMC`` sentences for N cars lapping an SMSP-anchored
track at varying speeds, with valid checksums, real latitude/longitude, RTK fix quality,
speed-over-ground and course-over-ground. This is the exact wire data the in-car GNSS units
(specs/11) would emit and that RaceSync ingests (``NmeaGpsSource`` / ``UdpTelemetrySource``)
to drive injection into Assetto Corsa (specs/05, specs/12).

Use it to exercise the full chain — ingestion -> fusion -> injection — end to end without a
car or a live receiver, and to feed the AC companion during the Phase-1 spike.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .model import local_to_geodetic
from .track import TrackFrame

# Sydney Motorsport Park, Gardner GP — approximate reference point (specs/02 TBC-1).
SMSP_REF_LAT = -33.80175
SMSP_REF_LON = 150.87090


def make_smsp_track(length_target: float = 3896.0, name: str = "SMSP (synthetic)") -> TrackFrame:
    """An SMSP-anchored closed centreline (~3.896 km) with a geodetic reference.

    A smooth closed loop (good enough to generate plausible lat/lon traces); replace with a
    surveyed SMSP centreline via ``TrackFrame.from_geojson_line`` once available.
    """
    n = 96
    a, b = 760.0, 320.0  # semi-axes (m); perimeter scaled to the target below
    pts = [(a * math.cos(2 * math.pi * i / n), b * math.sin(2 * math.pi * i / n))
           for i in range(n)]
    frame = TrackFrame(pts, name=name)
    scale = length_target / frame.length
    scaled = [(x * scale, y * scale) for x, y in pts]
    return TrackFrame(scaled, ref=(SMSP_REF_LAT, SMSP_REF_LON), name=name)


# --------------------------------------------------------------------------- #
# NMEA formatting helpers
# --------------------------------------------------------------------------- #

def nmea_checksum(body: str) -> str:
    cks = 0
    for ch in body:
        cks ^= ord(ch)
    return f"{cks:02X}"


def _sentence(body: str) -> str:
    """Wrap a body (no leading $) with '$' and '*HH' checksum."""
    return f"${body}*{nmea_checksum(body)}"


def _deg_to_dm(value: float, is_lat: bool) -> tuple[str, str]:
    """Decimal degrees -> NMEA (d)ddmm.mmmm + hemisphere."""
    hemi = ("N" if value >= 0 else "S") if is_lat else ("E" if value >= 0 else "W")
    v = abs(value)
    deg = int(v)
    minutes = (v - deg) * 60.0
    if is_lat:
        return f"{deg:02d}{minutes:07.4f}", hemi
    return f"{deg:03d}{minutes:07.4f}", hemi


def _hhmmss(base_epoch: float, t: float) -> str:
    """UTC time-of-day hhmmss.ss from base epoch (seconds) + elapsed t."""
    tod = (base_epoch + t) % 86400.0
    hh = int(tod // 3600)
    mm = int((tod % 3600) // 60)
    ss = tod % 60.0
    return f"{hh:02d}{mm:02d}{ss:05.2f}"


def _ddmmyy(base_epoch: float) -> str:
    # Fixed nominal date for the sample; real receivers send the live date.
    return "010126"  # 01 Jan 2026


def gga(lat: float, lon: float, t: float, base_epoch: float,
        fix_quality: int = 4, sats: int = 18, hdop: float = 0.6,
        alt: float = 30.0, talker: str = "GN") -> str:
    lat_s, lat_h = _deg_to_dm(lat, True)
    lon_s, lon_h = _deg_to_dm(lon, False)
    body = (f"{talker}GGA,{_hhmmss(base_epoch, t)},{lat_s},{lat_h},{lon_s},{lon_h},"
            f"{fix_quality},{sats:02d},{hdop:.1f},{alt:.1f},M,46.9,M,,")
    return _sentence(body)


def rmc(lat: float, lon: float, speed_mps: float, heading_rad: float, t: float,
        base_epoch: float, talker: str = "GN") -> str:
    lat_s, lat_h = _deg_to_dm(lat, True)
    lon_s, lon_h = _deg_to_dm(lon, False)
    sog_knots = speed_mps / 0.514444
    cog_deg = (math.degrees(heading_rad)) % 360.0
    body = (f"{talker}RMC,{_hhmmss(base_epoch, t)},A,{lat_s},{lat_h},{lon_s},{lon_h},"
            f"{sog_knots:05.1f},{cog_deg:05.1f},{_ddmmyy(base_epoch)},,")
    return _sentence(body)


# --------------------------------------------------------------------------- #
# Car field generation
# --------------------------------------------------------------------------- #

@dataclass
class CarSim:
    car_id: str
    base_speed: float        # m/s
    start_s: float           # starting fraction around the lap (grid stagger)
    speed_wobble: float = 0.0  # +/- m/s sinusoidal variation around the lap


def default_field(n: int = 10, base: float = 45.0, step: float = 1.6) -> list[CarSim]:
    """N cars with distinct, varying speeds and a staggered grid start.

    Speeds run from ``base`` upward in ``step`` increments (so each car laps at a
    different pace), with a small per-car cornering wobble for realism.
    """
    cars = []
    for i in range(n):
        cars.append(CarSim(
            car_id=f"{i + 1:02d}",
            base_speed=base + i * step,
            start_s=(i / max(n, 1)) * 0.04,   # ~grid spacing near start/finish
            speed_wobble=1.5 + (i % 3) * 0.5,
        ))
    return cars


def car_speed(car: CarSim, s: float) -> float:
    """Instantaneous speed: base + cornering wobble (slower 'in corners')."""
    return car.base_speed + car.speed_wobble * math.sin(2 * math.pi * (2 * s))


@dataclass
class Sample:
    t: float
    car_id: str
    lat: float
    lon: float
    speed: float
    heading: float


def simulate(track: TrackFrame, cars: list[CarSim], rate_hz: float = 10.0,
             duration_s: float = 60.0, base_epoch: float = 0.0) -> list[Sample]:
    """Advance each car around the track, sampling position at ``rate_hz``.

    Speed varies around the lap, so distance is integrated step-by-step (not a closed
    form). Returns time-ordered samples across all cars.
    """
    dt = 1.0 / rate_hz
    steps = int(duration_s * rate_hz)
    # Per-car cumulative distance along the track.
    dist = {c.car_id: c.start_s * track.length for c in cars}
    samples: list[Sample] = []
    for step in range(steps):
        t = round(step * dt, 3)
        for c in cars:
            s = (dist[c.car_id] / track.length) % 1.0
            x, y, heading = track.point_at(s)
            lat, lon = local_to_geodetic(x, y, track.ref[0], track.ref[1])
            v = car_speed(c, s)
            samples.append(Sample(t, c.car_id, lat, lon, v, heading))
            dist[c.car_id] += v * dt
    samples.sort(key=lambda smp: (smp.t, smp.car_id))
    return samples


def sample_to_nmea(s: Sample, base_epoch: float = 0.0) -> tuple[str, str]:
    """Render a sample as its (GGA, RMC) sentence pair."""
    return (gga(s.lat, s.lon, s.t, base_epoch),
            rmc(s.lat, s.lon, s.speed, s.heading, s.t, base_epoch))
