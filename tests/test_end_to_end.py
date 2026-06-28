"""End-to-end: NMEA in -> RaceSync -> phantom packets -> sim-side world state.

Exercises the whole chain the real system runs (minus AC itself): generated GPS sentences
are ingested, fused, encoded as phantom packets by the AC adapter, sent over the wire
(captured), and decoded by the PhantomReceiver back into world state. Proves the transport
and coordinate round-trip, not just the units in isolation.
"""

import importlib.util
from pathlib import Path

import pytest

from racesync.fusion import Fusion
from racesync.injection import PhantomReceiver, PhantomState
from racesync.injection.assetto_corsa import AssettoCorsaAdapter
from racesync.injection.base import GlobalSimState
from racesync.simgen import default_field, make_smsp_track, sample_to_nmea, simulate
from racesync.sources.gps_nmea import NmeaGpsSource


def test_nmea_to_simside_world(tmp_path):
    track = make_smsp_track()
    cars = default_field(6)
    samples = simulate(track, cars, rate_hz=10.0, duration_s=3.0)

    # Write per-car NMEA, like the gen-nmea CLI.
    streams = {c.car_id: [] for c in cars}
    for s in samples:
        g, r = sample_to_nmea(s)
        streams[s.car_id].extend((g, r))

    # Ingest -> fuse -> inject (AC adapter) -> capture wire -> receiver -> world.
    fusion = Fusion(track)
    sent = []
    adapter = AssettoCorsaAdapter(sender=sent.append)
    adapter.connect()
    receiver = PhantomReceiver()

    for fix in NmeaGpsSource(streams).stream():
        est = fusion.on_fix(fix)
        adapter.apply(PhantomState.from_estimate(est))
    adapter.set_global_state(GlobalSimState(code60=True))

    for packet in sent:
        receiver.ingest(packet)

    # All 6 cars made it through to sim-side world state...
    assert set(receiver.world()) == {c.car_id for c in cars}
    # ...and each phantom sits on the track centreline (sub-metre after the round-trip).
    for car_id, phantom in receiver.world().items():
        proj = track.project(phantom.x, phantom.y)
        assert proj.distance < 1.0, (car_id, proj.distance)
    # Global Code 60 propagated.
    assert receiver.global_state.code60 is True


def _load_ac_app():
    path = (Path(__file__).resolve().parent.parent
            / "tools" / "ac_companion" / "RaceSyncPhantoms" / "RaceSyncPhantoms.py")
    spec = importlib.util.spec_from_file_location("racesync_ac_app", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ac_companion_logic_runs_without_ac():
    """The AC app imports without AC present and its pure decode logic works."""
    app = _load_ac_app()
    assert app.ac is None                      # AC not importable here -> graceful
    app.phantoms.clear(); app.last_seq.clear()
    app.global_state.update({"code60": False, "chequered": False})

    # Feed it the same packets RaceSync sends.
    from racesync.injection.assetto_corsa import encode_global_packet, encode_phantom_packet
    app._handle_packet(encode_phantom_packet(PhantomState("03", 1.0, 12.0, -8.0, 1.5, 50.0)))
    app._handle_packet(encode_global_packet(GlobalSimState(code60=True)))

    assert "03" in app.phantoms
    assert app.phantoms["03"]["x"] == 12.0
    assert app.global_state["code60"] is True
    assert app._banner_text() == "*** CODE 60 ***"


def test_ac_companion_drops_stale_seq():
    app = _load_ac_app()
    app.phantoms.clear(); app.last_seq.clear()
    from racesync.injection.assetto_corsa import encode_phantom_packet
    app._handle_packet(encode_phantom_packet(PhantomState("1", 0.0, 1.0, 1.0, 0.0), seq=5))
    app._handle_packet(encode_phantom_packet(PhantomState("1", 0.0, 9.0, 9.0, 0.0), seq=2))
    assert app.phantoms["1"]["x"] == 1.0       # stale seq ignored
