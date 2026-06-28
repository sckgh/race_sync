import pytest

from racesync.fusion import Fusion, DEAD_RECKON_MAX_AGE
from racesync.model import (
    PositionSourceKind,
    TimingEvent,
    TimingEventKind,
)
from racesync.sources.base import RawFix
from racesync.track import TrackFrame


def square(side=400.0):
    h = side / 2
    return TrackFrame([(-h, -h), (h, -h), (h, h), (-h, h)], name="sq")


def test_fix_is_mapmatched_to_track_s():
    t = square(400.0)
    f = Fusion(t)
    # Point on the bottom edge midpoint -> s = 1/8.
    est = f.on_fix(RawFix(car_id="1", t=0.0, x=0.0, y=-200.0, speed=10.0))
    assert est.lap_distance.s == pytest.approx(1 / 8, abs=1e-6)
    assert est.source == PositionSourceKind.GPS
    assert est.car_id == "1"


def test_timing_lap_completed_sets_lap_count_and_fuses():
    t = square()
    f = Fusion(t)
    f.on_timing_event(TimingEvent(TimingEventKind.LAP_COMPLETED, t=10.0, car_id="1", lap=3))
    est = f.on_fix(RawFix(car_id="1", t=10.5, x=0.0, y=-200.0))
    assert est.lap_distance.lap == 3
    # Within the anchor window after a crossing -> FUSED quality.
    assert est.source == PositionSourceKind.FUSED


def test_lap_rollover_without_timing():
    t = square()
    f = Fusion(t)
    # Near end of lap (s ~ 0.97), then just past start/finish (s ~ 0.02): lap increments.
    # Bottom-left corner is s=0; just before it (left edge, near bottom) is s ~ 0.97.
    f.on_fix(RawFix(car_id="1", t=0.0, x=-200.0, y=-180.0))  # left edge near bottom
    before = f.latest("1")
    assert before.lap_distance.s > 0.9
    f.on_fix(RawFix(car_id="1", t=1.0, x=-180.0, y=-200.0))  # just past S/F on bottom edge
    after = f.latest("1")
    assert after.lap_distance.s < 0.1
    assert after.lap_distance.lap == before.lap_distance.lap + 1


def test_dead_reckoning_advances_position():
    t = square(400.0)  # length 1600 m
    f = Fusion(t)
    f.on_fix(RawFix(car_id="1", t=0.0, x=0.0, y=-200.0, speed=160.0, heading=0.0))
    # 1 s later at 160 m/s -> advanced 160 m = 0.1 lap.
    est = f.extrapolate("1", now=1.0)
    assert est is not None
    assert est.source == PositionSourceKind.DEAD_RECKONED
    assert est.lap_distance.s == pytest.approx(1 / 8 + 0.1, abs=1e-3)


def test_dead_reckoning_stops_when_too_stale():
    t = square()
    f = Fusion(t)
    f.on_fix(RawFix(car_id="1", t=0.0, x=0.0, y=-200.0, speed=50.0))
    est = f.extrapolate("1", now=DEAD_RECKON_MAX_AGE + 1.0)
    # Beyond the dead-reckon horizon: degrade in place (don't fabricate motion).
    assert est.source != PositionSourceKind.DEAD_RECKONED
    assert est.quality < 1.0


def test_order_by_progress():
    t = square()
    f = Fusion(t)
    f.on_timing_event(TimingEvent(TimingEventKind.LAP_COMPLETED, t=0.0, car_id="2", lap=2))
    f.on_fix(RawFix(car_id="1", t=1.0, x=0.0, y=-200.0))     # lap 0, s=1/8
    f.on_fix(RawFix(car_id="2", t=1.0, x=-200.0, y=0.0))     # lap 2, somewhere
    assert f.order()[0] == "2"  # car 2 is two laps ahead


def test_extrapolate_unknown_car_returns_none():
    f = Fusion(square())
    assert f.extrapolate("nope", now=1.0) is None
