import json

import pytest

from racesync.injection import (
    GlobalSimState,
    InjectionHarness,
    LatencyStats,
    LatencyTargets,
    LoopbackAdapter,
    PhantomState,
    SimInjectionAdapter,
    Verdict,
)
from racesync.injection.assetto_corsa import (
    AssettoCorsaAdapter,
    encode_global_packet,
    encode_phantom_packet,
)
from racesync.injection.harness import _percentile, score
from racesync.model import LapDistance, PositionEstimate, PositionSourceKind


def est(car_id="1", t=0.0, x=10.0, y=20.0, heading=0.5, speed=55.0, quality=1.0):
    return PositionEstimate(
        car_id=car_id, t=t, x=x, y=y,
        lap_distance=LapDistance(lap=0, s=0.1),
        source=PositionSourceKind.GPS, heading=heading, speed=speed, quality=quality,
    )


# -- phantom state + loopback adapter -------------------------------------- #

def test_phantom_from_estimate():
    p = PhantomState.from_estimate(est(heading=0.5))
    assert p.car_id == "1" and p.x == 10.0 and p.heading == 0.5


def test_loopback_records_and_autospawns():
    a = LoopbackAdapter()
    a.connect()
    a.apply(PhantomState.from_estimate(est(car_id="7")))
    assert "7" in a.spawned          # auto-spawned on first apply
    assert a.apply_count == 1
    assert a.latest("7").car_id == "7"


def test_loopback_requires_connect():
    a = LoopbackAdapter()
    with pytest.raises(RuntimeError):
        a.apply(PhantomState.from_estimate(est()))


def test_loopback_global_state():
    a = LoopbackAdapter()
    a.connect()
    a.set_global_state(GlobalSimState(code60=True))
    assert a.global_state.code60 is True


def test_loopback_is_a_sim_injection_adapter():
    assert isinstance(LoopbackAdapter(), SimInjectionAdapter)


# -- latency stats / scoring ----------------------------------------------- #

def test_percentile_interpolates():
    vals = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert _percentile(vals, 0) == 0.0
    assert _percentile(vals, 50) == 2.0
    assert _percentile(vals, 100) == 4.0
    assert _percentile(vals, 95) == pytest.approx(3.8)


def test_stats_from_samples():
    s = LatencyStats.from_samples([0.1, 0.2, 0.3, 0.4])
    assert s.n == 4
    assert s.min == 0.1 and s.max == 0.4
    assert s.mean == pytest.approx(0.25)


def test_score_verdicts():
    t = LatencyTargets(typical=0.25, degraded=0.5)
    assert score(LatencyStats.from_samples([0.1, 0.2]), t) == Verdict.PASS
    assert score(LatencyStats.from_samples([0.4, 0.45]), t) == Verdict.MARGINAL
    assert score(LatencyStats.from_samples([0.7, 0.8]), t) == Verdict.FAIL
    assert score(LatencyStats.from_samples([]), t) == Verdict.FAIL


# -- harness --------------------------------------------------------------- #

def test_harness_simulation_mode_pass():
    a = LoopbackAdapter(); a.connect()
    h = InjectionHarness(a)
    report = h.run([est(t=0.0), est(t=0.1), est(t=0.2)],
                   latency_model=lambda i, e: 0.08)  # 80 ms each
    assert a.apply_count == 3
    assert report.verdict == Verdict.PASS
    assert report.stats.p50 == pytest.approx(0.08)


def test_harness_simulation_mode_fail():
    a = LoopbackAdapter(); a.connect()
    h = InjectionHarness(a)
    report = h.run([est(t=0.0), est(t=0.1)], latency_model=lambda i, e: 0.9)
    assert report.verdict == Verdict.FAIL


def test_harness_live_mode_uses_clock():
    a = LoopbackAdapter(); a.connect()
    ticks = iter([0.05, 0.12])  # clock readings after each apply
    h = InjectionHarness(a, clock=lambda: next(ticks))
    # estimates captured at t=0 -> latency equals the clock reading.
    h.inject(est(t=0.0))
    h.inject(est(t=0.0))
    assert h.samples == [0.05, 0.12]


def test_harness_clamps_negative_latency():
    a = LoopbackAdapter(); a.connect()
    h = InjectionHarness(a, clock=lambda: 0.0)
    lat = h.inject(est(t=1.0))  # clock behind capture time -> negative -> clamped
    assert lat == 0.0
    assert any("clock skew" in n for n in h.notes)


def test_empty_report_is_fail():
    a = LoopbackAdapter(); a.connect()
    h = InjectionHarness(a)
    r = h.report()
    assert r.verdict == Verdict.FAIL
    assert any("no samples" in n for n in r.notes)


# -- assetto corsa adapter ------------------------------------------------- #

def test_ac_packet_encoding_is_valid_json():
    p = PhantomState.from_estimate(est(car_id="12", t=1.5, x=3.14159, y=2.71828,
                                       heading=1.2345, speed=50.0, quality=0.9))
    raw = encode_phantom_packet(p, seq=42)
    assert raw.endswith(b"\n")
    obj = json.loads(raw)
    assert obj["car"] == "12" and obj["seq"] == 42 and obj["v"] == 1
    assert obj["x"] == 3.142 and obj["q"] == 0.9


def test_ac_global_packet():
    obj = json.loads(encode_global_packet(GlobalSimState(code60=True, chequered=False)))
    assert obj["global"]["code60"] is True


def test_ac_adapter_sends_via_injected_sender():
    sent = []
    a = AssettoCorsaAdapter(sender=sent.append)
    a.connect()
    a.spawn("1")
    a.apply(PhantomState.from_estimate(est(car_id="1")))
    a.apply(PhantomState.from_estimate(est(car_id="1", t=0.1)))
    a.set_global_state(GlobalSimState(code60=True))
    assert a.sent_count == 3
    assert len(sent) == 3
    # Sequence numbers increment across phantom packets.
    seqs = [json.loads(p)["seq"] for p in sent[:2]]
    assert seqs == [0, 1]
    assert a.health()["phantoms"] == 1
