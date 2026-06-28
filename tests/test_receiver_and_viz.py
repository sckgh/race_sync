import pytest

from racesync.injection import LoopbackAdapter, PhantomReceiver, PhantomState
from racesync.injection.assetto_corsa import (
    AssettoCorsaAdapter,
    decode_global_packet,
    decode_phantom_packet,
    encode_global_packet,
    encode_phantom_packet,
)
from racesync.injection.base import GlobalSimState
from racesync.model import LapDistance, PositionEstimate, PositionSourceKind
from racesync.track import TrackFrame
from racesync.viz import track_ascii, track_svg


def est(car_id="1", x=10.0, y=20.0, source=PositionSourceKind.GPS):
    return PositionEstimate(car_id=car_id, t=0.0, x=x, y=y,
                            lap_distance=LapDistance(0, 0.1), source=source,
                            heading=0.3, speed=50.0)


def square(side=400.0):
    h = side / 2
    return TrackFrame([(-h, -h), (h, -h), (h, h), (-h, h)])


# -- phantom decode / receiver --------------------------------------------- #

def test_phantom_encode_decode_round_trip():
    p = PhantomState(car_id="12", t=1.5, x=3.0, y=4.0, heading=1.2, speed=50.0, quality=0.9)
    state, seq = decode_phantom_packet(encode_phantom_packet(p, seq=5))
    assert state.car_id == "12" and seq == 5
    assert state.x == 3.0 and state.heading == 1.2 and state.quality == 0.9


def test_decode_rejects_global_and_garbage():
    assert decode_phantom_packet(b"garbage") is None
    assert decode_phantom_packet(encode_global_packet(GlobalSimState(code60=True))) is None
    assert decode_global_packet(b"{}") is None


def test_receiver_tracks_world_and_global_state():
    r = PhantomReceiver()
    r.ingest(encode_phantom_packet(PhantomState("1", 0.0, 1.0, 2.0, 0.0), seq=0))
    r.ingest(encode_phantom_packet(PhantomState("2", 0.0, 3.0, 4.0, 0.0), seq=1))
    r.ingest(encode_global_packet(GlobalSimState(code60=True)))
    assert set(r.world()) == {"1", "2"}
    assert r.latest("2").x == 3.0
    assert r.global_state.code60 is True
    assert r.received == 3


def test_receiver_drops_stale_out_of_order():
    r = PhantomReceiver()
    r.ingest(encode_phantom_packet(PhantomState("1", 0.0, 1.0, 1.0, 0.0), seq=5))
    # An older sequence number for the same car is discarded.
    applied = r.ingest(encode_phantom_packet(PhantomState("1", 0.0, 9.0, 9.0, 0.0), seq=3))
    assert applied is None
    assert r.dropped_stale == 1
    assert r.latest("1").x == 1.0  # unchanged


def test_full_wire_loop_adapter_to_receiver():
    """encode (adapter) -> bytes -> decode (receiver): the whole RaceSync->sim path."""
    sent = []
    adapter = AssettoCorsaAdapter(sender=sent.append)
    adapter.connect()
    receiver = PhantomReceiver()
    for cid in ("1", "2", "3"):
        adapter.apply(PhantomState.from_estimate(est(car_id=cid, x=float(cid) * 5)))
    adapter.set_global_state(GlobalSimState(code60=True))
    for packet in sent:
        receiver.ingest(packet)
    assert set(receiver.world()) == {"1", "2", "3"}
    assert receiver.global_state.code60 is True


# -- visualizer ------------------------------------------------------------ #

def test_svg_contains_track_and_cars():
    t = square()
    cars = [est("1", -200, 0), est("2", 0, -200), est("3", 200, 0)]
    svg = track_svg(t, cars, title="SMSP", banner="GREEN")
    assert svg.startswith("<svg")
    assert "<polygon" in svg                 # the track outline
    assert svg.count("<circle") >= 4         # 3 cars + start/finish marker
    assert "SMSP" in svg and "GREEN" in svg


def test_svg_escapes_text():
    t = square()
    svg = track_svg(t, [], title="A & B <x>")
    assert "&amp;" in svg and "&lt;x&gt;" in svg


def test_ascii_map_renders_cars():
    t = square()
    cars = [est("1", -200, 0), est("2", 0, 200)]
    art = track_ascii(t, cars, width=40, height=16)
    lines = art.splitlines()
    assert len(lines) == 16
    assert any("." in line for line in lines)       # track drawn
    assert any("1" in line or "2" in line for line in lines)  # cars drawn
