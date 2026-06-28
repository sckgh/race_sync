import pytest

from racesync.bus import EventBus
from racesync.model import TimingEvent, TimingEventKind
from racesync.sources.base import RawFix
from racesync.sources.replay import ReplaySource
from racesync.sources.mylaps import MyLapsX2Source


def test_bus_pubsub_and_unsubscribe():
    bus = EventBus()
    got = []
    unsub = bus.subscribe("topic", got.append)
    bus.publish("topic", 1)
    bus.publish("topic", 2)
    unsub()
    bus.publish("topic", 3)
    assert got == [1, 2]


def test_bus_aggregates_handler_errors():
    bus = EventBus()
    delivered = []
    bus.subscribe("t", lambda e: (_ for _ in ()).throw(ValueError("boom")))
    bus.subscribe("t", delivered.append)
    with pytest.raises(ExceptionGroup):
        bus.publish("t", "x")
    # The second handler still ran despite the first raising.
    assert delivered == ["x"]


def test_bus_recording():
    bus = EventBus()
    bus.start_recording()
    bus.publish("a", 1)
    bus.publish("b", 2)
    assert list(bus.history()) == [("a", 1), ("b", 2)]
    assert list(bus.history("a")) == [("a", 1)]


def test_replay_round_trip(tmp_path):
    records = [
        {"type": "fix", "car_id": "1", "t": 0.0, "x": 1.0, "y": 2.0, "speed": 50.0},
        {"type": "fix", "car_id": "1", "t": 0.1, "lat": -33.8, "lon": 150.87},
        {"type": "timing", "kind": "lap_completed", "t": 95.0, "car_id": "1", "lap": 1},
        {"type": "timing", "kind": "race_completed", "t": 7000.0, "car_id": "1", "lap": 77},
    ]
    src = ReplaySource.from_records(records, tmp_path / "feed.jsonl")
    events = list(src.stream())
    assert len(events) == 4
    assert isinstance(events[0], RawFix)
    assert isinstance(events[2], TimingEvent)
    assert events[3].kind == TimingEventKind.RACE_COMPLETED
    assert events[3].lap == 77


def test_mylaps_stub_emits_events():
    src = MyLapsX2Source()
    src.feed_passing("1", t=1.0, loop="sf")
    src.feed_lap("1", t=95.0, lap=1, lap_time=94.0)
    src.feed_race_completed("1", t=7000.0, lap=77)
    events = list(src.stream())
    assert [e.kind for e in events] == [
        TimingEventKind.PASSING,
        TimingEventKind.LAP_COMPLETED,
        TimingEventKind.RACE_COMPLETED,
    ]
    assert events[1].value == 94.0
