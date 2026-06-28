import pytest

from racesync.injection.assetto_corsa import encode_global_packet, encode_phantom_packet
from racesync.injection.base import GlobalSimState, PhantomState
from racesync.injection.shm_bridge import (
    FRAME_SIZE,
    MAX_CARS,
    ShmBridge,
    car_number,
    pack_frame,
    unpack_frame,
)


def test_car_number_numeric_and_hash():
    assert car_number("07") == 7
    assert car_number("V1") != 0
    assert car_number("V1") == car_number("V1")  # stable


def test_pack_unpack_round_trip():
    world = {
        "1": PhantomState("1", 0.0, 10.0, 20.0, 1.2, 55.0, 1.0),
        "V2": PhantomState("V2", 0.0, -5.0, 8.0, 0.3, 40.0, 0.5),
    }
    frame = pack_frame(world, code60=True, chequered=False, seq=42)
    assert len(frame) == FRAME_SIZE
    out = unpack_frame(frame)
    assert out["count"] == 2 and out["seq"] == 42
    assert out["code60"] is True and out["chequered"] is False
    by_id = {c["id"]: c for c in out["cars"]}
    assert by_id[1]["x"] == pytest.approx(10.0)
    assert by_id[1]["heading"] == pytest.approx(1.2)
    assert by_id[car_number("V2")]["quality"] == pytest.approx(0.5)


def test_pack_truncates_beyond_max_cars():
    world = {str(i): PhantomState(str(i), 0.0, float(i), 0.0, 0.0, 0.0, 1.0)
             for i in range(MAX_CARS + 10)}
    out = unpack_frame(pack_frame(world))
    assert out["count"] == MAX_CARS
    assert len(out["cars"]) == MAX_CARS


def test_unpack_rejects_bad_data():
    with pytest.raises(ValueError):
        unpack_frame(b"short")
    with pytest.raises(ValueError):
        unpack_frame(b"\x00" * FRAME_SIZE)  # bad magic


def test_bridge_ingests_packets_into_frame():
    bridge = ShmBridge()
    bridge.ingest(encode_phantom_packet(PhantomState("3", 0.0, 1.0, 2.0, 0.5, 30.0, 1.0)))
    bridge.ingest(encode_global_packet(GlobalSimState(code60=True)))
    out = unpack_frame(bridge.frame())
    assert out["count"] == 1
    assert out["code60"] is True
    assert out["seq"] == 1
    assert unpack_frame(bridge.frame())["seq"] == 2  # advances
