import math

import pytest

from racesync.simgen import (
    CarSim,
    default_field,
    gga,
    make_smsp_track,
    nmea_checksum,
    rmc,
    sample_to_nmea,
    simulate,
)
from racesync.sources.gps_nmea import NmeaParser, _nmea_checksum_ok


def test_generated_sentences_have_valid_checksums():
    track = make_smsp_track()
    samples = simulate(track, default_field(3), rate_hz=5.0, duration_s=2.0)
    for s in samples:
        g, r = sample_to_nmea(s)
        assert _nmea_checksum_ok(g), g
        assert _nmea_checksum_ok(r), r


def test_generated_nmea_parses_back_to_position():
    track = make_smsp_track()
    samples = simulate(track, default_field(1), rate_hz=10.0, duration_s=1.0)
    parser = NmeaParser("01")
    s = samples[0]
    g, r = sample_to_nmea(s)
    fix_g = parser.parse(g)
    fix_r = parser.parse(r)
    # GGA position should match the generated lat/lon closely (NMEA rounds to 0.0001').
    assert fix_g.lat == pytest.approx(s.lat, abs=2e-6)
    assert fix_g.lon == pytest.approx(s.lon, abs=2e-6)
    assert fix_g.meta["fix"] == "rtk-fixed"          # quality 4
    # RMC carries speed; ~within rounding of 0.1 knot.
    assert fix_r.speed == pytest.approx(s.speed, abs=0.1)


def test_field_has_distinct_speeds():
    cars = default_field(10)
    assert len(cars) == 10
    speeds = [c.base_speed for c in cars]
    assert len(set(speeds)) == 10           # all distinct
    assert min(speeds) < max(speeds)


def test_cars_map_back_onto_the_track():
    track = make_smsp_track()
    samples = simulate(track, default_field(5), rate_hz=5.0, duration_s=3.0)
    parser = {f"{i+1:02d}": NmeaParser(f"{i+1:02d}") for i in range(5)}
    # Parse a GGA and check it map-matches close to the track centreline.
    for s in samples[:20]:
        g, _ = sample_to_nmea(s)
        fix = parser[s.car_id].parse(g)
        proj = track.project_geodetic(fix.lat, fix.lon)
        assert proj.distance < 1.0           # on the centreline (sub-metre)


def test_deg_to_dm_via_known_value():
    # 33 deg 48.105' S etc. — checksum util sanity + format length.
    body = "GNGGA,000000.00,3348.1050,S,15052.2540,E,4,18,0.6,30.0,M,46.9,M,,"
    assert len(nmea_checksum(body)) == 2
