import pytest

from racesync.console import OperatorConsole
from racesync.health import HealthMonitor
from racesync.injection.base import LoopbackAdapter
from racesync.model import RaceState, TimingEvent, TimingEventKind
from racesync.scoring import CarClass, Entry, ScoringService
from racesync.state_engine import RaceStateEngine


def build(clock_t=0.0):
    engine = RaceStateEngine()
    health = HealthMonitor(state_engine=engine)
    scoring = ScoringService(state_engine=engine)
    scoring.register(Entry("1", "1", CarClass.REAL, "A. Real", "B"))
    scoring.register(Entry("V1", "V1", CarClass.VIRTUAL, "S. Sim"))
    adapter = LoopbackAdapter(); adapter.connect()
    console = OperatorConsole(engine, health, scoring, adapter=adapter, clock=lambda: clock_t)
    return console, engine, scoring, adapter


def test_arm_and_green_flow():
    console, engine, _, _ = build()
    assert console.dispatch("arm").ok
    assert engine.state == RaceState.FORMATION
    res = console.dispatch("green")
    assert res.ok and engine.state == RaceState.GREEN


def test_illegal_command_is_reported_not_raised():
    console, engine, _, _ = build()
    res = console.dispatch("green")  # cannot go green from PRE_RACE
    assert not res.ok
    assert "not allowed" in res.message
    assert engine.state == RaceState.PRE_RACE  # unchanged


def test_code60_drives_engine_and_adapter():
    console, engine, _, adapter = build()
    console.dispatch("arm")
    console.dispatch("green")
    res = console.dispatch("code60 on")
    assert res.ok and engine.is_code60
    assert adapter.global_state.code60 is True
    console.dispatch("code60 off")
    assert engine.state == RaceState.GREEN
    assert adapter.global_state.code60 is False


def test_code60_bad_args():
    console, *_ = build()
    console.dispatch("arm"); console.dispatch("green")
    res = console.dispatch("code60 maybe")
    assert not res.ok and "usage" in res.message


def test_chequer_requires_armed_finish():
    console, engine, scoring, adapter = build()
    console.dispatch("arm"); console.dispatch("green")
    res = console.dispatch("chequer")
    assert not res.ok  # finish not armed
    # Arm via timing, then it works and freezes scoring.
    engine.on_timing_event(TimingEvent(TimingEventKind.RACE_COMPLETED, t=0.0, car_id="1", lap=77))
    res = console.dispatch("chequer")
    assert res.ok and engine.state == RaceState.CHEQUERED
    assert adapter.global_state.chequered is True


def test_chequer_force_overrides():
    console, engine, *_ = build()
    console.dispatch("arm"); console.dispatch("green")
    res = console.dispatch("chequer force")
    assert res.ok and engine.state == RaceState.CHEQUERED


def test_penalty_applies_and_validates():
    console, _, scoring, _ = build()
    res = console.dispatch("penalty V1 1 overtake under code60")
    assert res.ok
    assert scoring.classify(CarClass.VIRTUAL).standings[0].score.lap_penalty == 1
    # Unknown car / bad laps are reported, not raised.
    assert not console.dispatch("penalty ZZ 1").ok
    assert not console.dispatch("penalty V1 two").ok


def test_render_shows_state_and_classes():
    console, engine, *_ = build()
    console.dispatch("arm"); console.dispatch("green")
    out = console.render()
    assert "OPERATOR CONSOLE" in out
    assert "GREEN" in out
    assert "REAL class" in out and "VIRTUAL class" in out


def test_render_shows_code60_banner_and_alarm():
    console, engine, _, _ = build()
    console.dispatch("arm"); console.dispatch("green")
    console.dispatch("code60 on")
    out = console.render()
    assert "CODE 60" in out


def test_run_loop_quits(capsys):
    console, *_ = build()
    cmds = iter(["arm", "green", "quit"])
    console.run(input_fn=lambda _prompt: next(cmds), output_fn=print)
    out = capsys.readouterr().out
    assert "bye" in out


def test_help_lists_commands():
    console, *_ = build()
    res = console.dispatch("help")
    assert res.ok and "code60" in res.message and "chequer" in res.message
