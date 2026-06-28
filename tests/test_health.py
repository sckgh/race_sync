import pytest

from racesync.bus import TOPIC_HEALTH, EventBus
from racesync.health import HealthMonitor, Status
from racesync.model import RaceState, TimingEvent, TimingEventKind
from racesync.sources.base import RawFix
from racesync.state_engine import RaceStateEngine


def fix(t, car="1"):
    return RawFix(car_id=car, t=t, x=0.0, y=0.0, speed=50.0)


def test_fresh_feed_is_go():
    h = HealthMonitor()
    for t in (0.0, 0.1, 0.2, 0.3):
        h.observe("gps", fix(t), now=t)
    snap = h.snapshot(now=0.35)
    assert snap.sources["gps"].status == Status.GO
    assert snap.overall == Status.GO
    assert snap.sources["gps"].rate_hz == pytest.approx(3 / 0.3, rel=1e-6)


def test_stale_feed_degrades_then_faults():
    h = HealthMonitor()  # defaults: fresh 0.5s, fault 2.0s
    h.observe("gps", fix(0.0), now=0.0)
    assert h.snapshot(now=1.0).overall == Status.DEGRADED   # 1.0s old
    assert h.snapshot(now=3.0).overall == Status.FAULT      # 3.0s old


def test_sparse_timing_source_uses_its_own_thresholds():
    h = HealthMonitor()
    h.register("timing", fresh=120.0, fault=300.0, critical=True)
    h.observe("timing", TimingEvent(TimingEventKind.LAP_COMPLETED, t=0.0, car_id="1", lap=1),
              now=0.0)
    # 90 s since last lap is normal for timing — should still be GO, not FAULT.
    assert h.snapshot(now=90.0).sources["timing"].status == Status.GO


def test_non_critical_source_does_not_drive_overall():
    h = HealthMonitor()
    h.register("aux", critical=False, fresh=0.5, fault=2.0)
    h.observe("aux", fix(0.0), now=0.0)
    snap = h.snapshot(now=10.0)  # very stale, but non-critical
    assert snap.sources["aux"].status == Status.FAULT
    assert snap.overall == Status.GO
    assert snap.alarms == []


def test_racing_on_stale_feed_raises_alarm():
    engine = RaceStateEngine()
    engine.arm(t=0.0)
    engine.go_green(t=0.0)
    h = HealthMonitor(state_engine=engine)
    h.observe("gps", fix(0.0), now=0.0)
    snap = h.snapshot(now=5.0)  # critical feed FAULT while GREEN
    assert snap.overall == Status.FAULT
    assert any("STALE POSITION DATA" in a for a in snap.alarms)


def test_tick_publishes_snapshot():
    bus = EventBus()
    seen = []
    bus.subscribe(TOPIC_HEALTH, seen.append)
    h = HealthMonitor(bus=bus)
    h.observe("gps", fix(0.0), now=0.0)
    snap = h.tick(now=0.1)
    assert seen == [snap]
    assert seen[0].overall == Status.GO
