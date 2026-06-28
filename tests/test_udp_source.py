import json

from racesync.sources.base import RawFix
from racesync.sources.gps_nmea import NmeaParser
from racesync.sources.udp import (
    UdpTelemetrySource,
    decode_telemetry_packet,
    encode_telemetry_packet,
)


def _nmea(body: str) -> bytes:
    cks = 0
    for ch in body:
        cks ^= ord(ch)
    return f"${body}*{cks:02X}".encode()


def test_encode_decode_round_trip():
    fix = RawFix(car_id="12", t=1.5, lat=-33.8, lon=150.87, speed=55.0, heading=1.2, quality=0.9)
    raw = encode_telemetry_packet(fix, seq=7)
    obj = json.loads(raw)
    assert obj["car"] == "12" and obj["seq"] == 7
    back = decode_telemetry_packet(raw)
    assert back.car_id == "12"
    assert back.lat == -33.8 and back.lon == 150.87
    assert back.speed == 55.0 and back.quality == 0.9
    assert back.meta["seq"] == 7


def test_decode_xy_packet():
    fix = RawFix(car_id="3", t=2.0, x=12.0, y=-4.0, speed=40.0)
    back = decode_telemetry_packet(encode_telemetry_packet(fix))
    assert back.x == 12.0 and back.y == -4.0


def test_decode_rejects_garbage_and_incomplete():
    assert decode_telemetry_packet(b"") is None
    assert decode_telemetry_packet(b"not json") is None
    assert decode_telemetry_packet(b'{"car":"1"}') is None  # missing t


def test_decode_nmea_payload_with_parser():
    parser = NmeaParser("9")
    fix = decode_telemetry_packet(_nmea("GNRMC,123519,A,3354.000,S,15052.200,E,010.0,084.4,230394,,"),
                                  nmea_parser=parser)
    assert fix is not None and fix.car_id == "9"


def test_nmea_payload_ignored_without_parser():
    assert decode_telemetry_packet(_nmea("GNGGA,123519,3354.0,S,15052.2,E,4,08,0.9,5,M,4,M,,")) is None


def test_source_streams_decoded_fixes():
    packets = [
        encode_telemetry_packet(RawFix(car_id="1", t=0.0, x=0.0, y=0.0, speed=50.0), seq=0),
        b"garbage",
        encode_telemetry_packet(RawFix(car_id="2", t=0.1, x=1.0, y=1.0, speed=52.0), seq=1),
    ]
    src = UdpTelemetrySource(packets=packets)
    fixes = list(src.stream())
    assert [f.car_id for f in fixes] == ["1", "2"]  # garbage dropped
