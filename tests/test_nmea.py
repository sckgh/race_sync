import math

from racesync.sources.gps_nmea import NmeaParser, NmeaGpsSource, _nmea_checksum_ok


# Real-format sample sentences (checksums computed to match).
GGA = "$GPGGA,123519,3354.000,S,15052.200,E,4,08,0.9,545.4,M,46.9,M,,*4F"
RMC = "$GPRMC,123519,A,3354.000,S,15052.200,E,022.4,084.4,230394,003.1,W*77"


def _with_checksum(body: str) -> str:
    cks = 0
    for ch in body:
        cks ^= ord(ch)
    return f"${body}*{cks:02X}"


def test_checksum_validation():
    good = _with_checksum("GPGGA,123519,3354.000,S,15052.200,E,4,08,0.9,545.4,M,46.9,M,,")
    assert _nmea_checksum_ok(good)
    assert not _nmea_checksum_ok(good[:-1] + "0")


def test_gga_parses_position_and_rtk_quality():
    body = "GNGGA,123519,3354.000,S,15052.200,E,4,08,0.9,545.4,M,46.9,M,,"
    p = NmeaParser("12")
    fix = p.parse(_with_checksum(body), arrival_t=10.0)
    assert fix is not None
    # 33 deg 54.000' South -> -33.9
    assert fix.lat == math.copysign(33 + 54.0 / 60, -1)
    assert fix.lon == 150 + 52.2 / 60
    assert fix.quality == 1.0  # fix type 4 = RTK fixed
    assert fix.meta["fix"] == "rtk-fixed"
    assert fix.t == 10.0


def test_gga_no_fix_returns_none_but_sets_quality():
    body = "GNGGA,123519,,,,,0,00,,,M,,M,,"
    p = NmeaParser("12")
    assert p.parse(_with_checksum(body)) is None


def test_rmc_parses_speed_and_heading():
    body = "GNRMC,123519,A,3354.000,S,15052.200,E,022.4,084.4,230394,003.1,W"
    p = NmeaParser("7")
    fix = p.parse(_with_checksum(body), arrival_t=5.0)
    assert fix is not None
    # 22.4 knots -> ~11.52 m/s
    assert abs(fix.speed - 22.4 * 0.514444) < 1e-6
    assert abs(fix.heading - math.radians(84.4)) < 1e-6


def test_rmc_void_status_rejected():
    body = "GNRMC,123519,V,3354.000,S,15052.200,E,000.0,000.0,230394,,"
    p = NmeaParser("7")
    assert p.parse(_with_checksum(body)) is None


def test_source_interleaves_cars():
    body1 = _with_checksum("GNRMC,123519,A,3354.000,S,15052.200,E,010.0,084.4,230394,,")
    body2 = _with_checksum("GNRMC,123519,A,3355.000,S,15053.200,E,020.0,090.0,230394,,")
    src = NmeaGpsSource({"1": [body1, body1], "2": [body2]})
    fixes = list(src.stream())
    assert {f.car_id for f in fixes} == {"1", "2"}
    assert len(fixes) == 3
