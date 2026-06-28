import pytest

from racesync.bus import TOPIC_STATE, EventBus
from racesync.model import RaceState, TimingEvent, TimingEventKind
from racesync.state_engine import InvalidTransition, RaceStateEngine


def test_happy_path_to_green():
    e = RaceStateEngine()
    assert e.state == RaceState.PRE_RACE
    e.arm(t=0.0)
    assert e.state == RaceState.FORMATION
    e.go_green(t=1.0)
    assert e.state == RaceState.GREEN
    assert e.green_t == 1.0


def test_illegal_transition_raises():
    e = RaceStateEngine()
    with pytest.raises(InvalidTransition):
        e.go_green(t=0.0)  # cannot go green from PRE_RACE


def test_code60_cycle_tracks_neutralised_time():
    e = RaceStateEngine()
    e.arm(t=0.0)
    e.go_green(t=1.0)
    e.set_code60(True, t=10.0)
    assert e.is_code60
    e.set_code60(False, t=25.0)  # 15 s neutralised
    assert e.state == RaceState.GREEN
    assert e.neutralised_seconds() == pytest.approx(15.0)
    # Multiple cycles accumulate.
    e.set_code60(True, t=30.0)
    e.set_code60(False, t=35.0)
    assert e.neutralised_seconds() == pytest.approx(20.0)


def test_finish_requires_arming():
    e = RaceStateEngine()
    e.arm(t=0.0)
    e.go_green(t=1.0)
    with pytest.raises(InvalidTransition):
        e.fire_chequer(t=100.0)
    # Authoritative timing arms the finish; then it fires.
    e.on_timing_event(TimingEvent(TimingEventKind.RACE_COMPLETED, t=99.0, car_id="1", lap=77))
    assert e.finish_armed
    e.fire_chequer(t=100.0)
    assert e.state == RaceState.CHEQUERED
    assert e.chequered_t == 100.0


def test_forced_finish_overrides_arming():
    e = RaceStateEngine()
    e.arm(t=0.0)
    e.go_green(t=1.0)
    e.fire_chequer(t=50.0, force=True)
    assert e.state == RaceState.CHEQUERED
    assert e.audit[-1].meta["forced"] is True


def test_chequer_from_neutralised_closes_window():
    e = RaceStateEngine()
    e.arm(t=0.0)
    e.go_green(t=1.0)
    e.set_code60(True, t=10.0)
    e.arm_finish(t=20.0, car_id="1")
    e.fire_chequer(t=21.0)
    assert e.state == RaceState.CHEQUERED
    # The open neutralisation is closed at the chequer, counted in fairness time.
    assert e.neutralised_seconds() == pytest.approx(11.0)


def test_terminal_state_blocks_further_transitions():
    e = RaceStateEngine()
    e.arm(t=0.0)
    e.go_green(t=1.0)
    e.fire_chequer(t=5.0, force=True)
    with pytest.raises(InvalidTransition):
        e.set_code60(True, t=6.0)


def test_transitions_published_on_bus_and_audited():
    bus = EventBus()
    seen = []
    bus.subscribe(TOPIC_STATE, seen.append)
    e = RaceStateEngine(bus=bus)
    e.arm(t=0.0)
    e.go_green(t=1.0)
    assert [s.to_state for s in seen] == [RaceState.FORMATION, RaceState.GREEN]
    assert len(e.audit) == 2
    assert e.audit[0].source == "operator"


def test_leader_tracking_and_start_skew():
    e = RaceStateEngine()
    e.arm(t=0.0)
    e.go_green(t=1.0)
    e.on_timing_event(TimingEvent(TimingEventKind.LEADER_CHANGED, t=2.0, car_id="9", lap=1))
    assert e.leader_car == "9"
    e.on_timing_event(TimingEvent(TimingEventKind.LAP_COMPLETED, t=90.0, car_id="9", lap=2))
    assert e.leader_lap == 2
    # Virtual field went green 0.4 s after the real field.
    assert e.start_skew(1.4) == pytest.approx(0.4)
