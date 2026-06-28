import pytest

from racesync.bus import EventBus
from racesync.fusion import Fusion
from racesync.model import (
    LapDistance,
    PositionEstimate,
    PositionSourceKind,
    TimingEvent,
    TimingEventKind,
)
from racesync.runner import Pipeline
from racesync.scoring import (
    CarClass,
    Entry,
    ScoringService,
    format_classification,
)
from racesync.sources.replay import ReplaySource
from racesync.state_engine import RaceStateEngine
from racesync.track import TrackFrame


def real(num, car_id=None, division="C", driver="Driver"):
    return Entry(car_id=car_id or num, number=num, klass=CarClass.REAL,
                 driver=driver, division=division)


def virtual(num, car_id=None, driver="SimRacer"):
    return Entry(car_id=car_id or num, number=num, klass=CarClass.VIRTUAL, driver=driver)


def lap(car_id, lap_no, t=0.0, value=None):
    return TimingEvent(TimingEventKind.LAP_COMPLETED, t=t, car_id=car_id, lap=lap_no, value=value)


def pos(car_id, lap_no, s, source=PositionSourceKind.GPS, quality=1.0):
    return PositionEstimate(
        car_id=car_id, t=0.0, x=0.0, y=0.0,
        lap_distance=LapDistance(lap=lap_no, s=s), source=source, quality=quality,
    )


def test_classes_are_separate():
    sc = ScoringService()
    sc.register(real("10"))
    sc.register(virtual("V1"))
    sc.on_timing_event(lap("10", 5))
    sc.on_timing_event(lap("V1", 3))
    real_c = sc.classify(CarClass.REAL)
    virt_c = sc.classify(CarClass.VIRTUAL)
    assert [s.score.entry.number for s in real_c.standings] == ["10"]
    assert [s.score.entry.number for s in virt_c.standings] == ["V1"]


def test_ranking_by_laps_then_position():
    sc = ScoringService()
    for n in ("1", "2", "3"):
        sc.register(real(n))
    sc.on_timing_event(lap("1", 5))
    sc.on_timing_event(lap("2", 5))
    sc.on_timing_event(lap("3", 4))
    # Same laps -> rank by track position (s).
    sc.on_position(pos("1", 5, 0.2))
    sc.on_position(pos("2", 5, 0.8))
    sc.on_position(pos("3", 4, 0.9))
    standings = sc.classify(CarClass.REAL).standings
    assert [s.score.entry.number for s in standings] == ["2", "1", "3"]
    assert standings[0].gap_laps == 0.0
    # Car 1 is 0.6 of a lap behind car 2.
    assert standings[1].gap_laps == pytest.approx(0.6)


def test_lap_penalty_demotes_in_classification():
    sc = ScoringService()
    sc.register(real("1"))
    sc.register(real("2"))
    sc.on_timing_event(lap("1", 10))
    sc.on_timing_event(lap("2", 9))
    assert sc.classify(CarClass.REAL).standings[0].score.entry.number == "1"
    # A 2-lap penalty drops car 1 below car 2.
    sc.add_penalty("1", laps=2, reason="CPS shortfall")
    standings = sc.classify(CarClass.REAL).standings
    assert standings[0].score.entry.number == "2"
    assert standings[1].score.lap_penalty == 2


def test_best_and_last_lap_tracked():
    sc = ScoringService()
    sc.register(real("1"))
    sc.on_timing_event(lap("1", 1, value=100.0))
    sc.on_timing_event(lap("1", 2, value=98.5))
    sc.on_timing_event(lap("1", 3, value=99.2))
    s = sc.classify(CarClass.REAL).standings[0].score
    assert s.best_lap == 98.5
    assert s.last_lap == 99.2


def test_data_quality_surfaced():
    sc = ScoringService()
    sc.register(real("1"))
    sc.on_position(pos("1", 2, 0.5, source=PositionSourceKind.DEAD_RECKONED, quality=0.3))
    s = sc.classify(CarClass.REAL).standings[0].score
    assert s.source == PositionSourceKind.DEAD_RECKONED
    assert s.quality == 0.3


def test_finalize_freezes_timed_finish_with_fairness():
    engine = RaceStateEngine()
    engine.arm(t=0.0)
    engine.go_green(t=1.0)
    engine.set_code60(True, t=10.0)
    engine.set_code60(False, t=20.0)  # 10 s neutralised
    sc = ScoringService(state_engine=engine)
    sc.register(virtual("V1"))
    sc.register(virtual("V2"))
    sc.on_position(pos("V1", 30, 0.4))
    sc.on_position(pos("V2", 30, 0.6))
    final = sc.finalize(t=100.0)
    virt = final[CarClass.VIRTUAL]
    assert virt.finished is True
    assert virt.at_t == 100.0
    # V2 further around at the chequer -> classified ahead.
    assert [s.score.entry.number for s in virt.standings] == ["V2", "V1"]
    assert virt.fairness["neutralised_seconds"] == pytest.approx(10.0)
    # After finalize, classify returns the frozen result even if data changes.
    sc.on_position(pos("V1", 40, 0.9))
    assert sc.classify(CarClass.VIRTUAL).standings[0].score.entry.number == "V2"


def test_attach_to_bus_updates_live(tmp_path):
    bus = EventBus()
    engine = RaceStateEngine(bus=bus)
    fusion = Fusion(TrackFrame([(-200, -200), (200, -200), (200, 200), (-200, 200)]))
    scoring = ScoringService(state_engine=engine)
    scoring.register(real("1"))
    scoring.attach(bus)

    feed = ReplaySource.from_records([
        {"type": "fix", "car_id": "1", "t": 0.0, "x": 0.0, "y": -200.0, "speed": 50.0},
        {"type": "timing", "kind": "lap_completed", "t": 1.0, "car_id": "1", "lap": 1, "value": 95.0},
    ], tmp_path / "f.jsonl")
    Pipeline(fusion, state_engine=engine, bus=bus).run([feed])

    s = scoring.classify(CarClass.REAL).standings[0].score
    assert s.laps == 1
    assert s.best_lap == 95.0
    assert s.source is not None  # position flowed through too


def test_format_classification_renders():
    sc = ScoringService()
    sc.register(real("10", division="A", driver="Jane Smith"))
    sc.on_timing_event(lap("10", 12, value=99.1))
    text = format_classification(sc.classify(CarClass.REAL))
    assert "REAL class" in text
    assert "Jane Smith" in text
    assert "10" in text
