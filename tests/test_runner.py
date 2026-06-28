import pytest

from racesync.bus import TOPIC_POSITION, TOPIC_STATE, TOPIC_TIMING, EventBus
from racesync.fusion import Fusion
from racesync.model import RaceState, TimingEventKind
from racesync.runner import Pipeline, merge_streams
from racesync.sources.mylaps import MyLapsX2Source
from racesync.sources.replay import ReplaySource
from racesync.state_engine import RaceStateEngine
from racesync.track import TrackFrame


def square(side=400.0):
    h = side / 2
    return TrackFrame([(-h, -h), (h, -h), (h, h), (-h, h)], name="sq")


def test_merge_orders_by_timestamp(tmp_path):
    a = ReplaySource.from_records([
        {"type": "fix", "car_id": "1", "t": 0.0, "x": 0.0, "y": -200.0},
        {"type": "fix", "car_id": "1", "t": 2.0, "x": 200.0, "y": 0.0},
    ], tmp_path / "a.jsonl")
    b = MyLapsX2Source(name="timing")
    b.feed_lap("1", t=1.0, lap=1)
    b.feed_lap("1", t=3.0, lap=2)
    merged = list(merge_streams([a, b]))
    times = [ev.t for _, ev in merged]
    assert times == [0.0, 1.0, 2.0, 3.0]
    # Names are preserved.
    assert merged[1][0] == "timing"


def test_pipeline_publishes_and_drives_state(tmp_path):
    bus = EventBus()
    positions, timings, states = [], [], []
    bus.subscribe(TOPIC_POSITION, positions.append)
    bus.subscribe(TOPIC_TIMING, timings.append)
    bus.subscribe(TOPIC_STATE, states.append)

    track = square()
    fusion = Fusion(track)
    engine = RaceStateEngine(bus=bus)
    engine.arm(t=-1.0)
    engine.go_green(t=0.0)
    engine.leader_car = "1"

    feed = ReplaySource.from_records([
        {"type": "fix", "car_id": "1", "t": 0.5, "x": 0.0, "y": -200.0, "speed": 50.0},
        {"type": "timing", "kind": "lap_completed", "t": 1.0, "car_id": "1", "lap": 1},
        {"type": "timing", "kind": "race_completed", "t": 2.0, "car_id": "1", "lap": 77},
    ], tmp_path / "f.jsonl")

    pipe = Pipeline(fusion, state_engine=engine, bus=bus)
    counts = pipe.run([feed])

    assert counts == {"fix": 1, "timing": 2}
    assert len(positions) == 1
    assert positions[0].car_id == "1"
    assert len(timings) == 2
    # race_completed armed the finish via the state engine.
    assert engine.finish_armed
    assert engine.leader_lap == 1


def test_pipeline_logical_now_tracks_latest(tmp_path):
    feed = ReplaySource.from_records([
        {"type": "fix", "car_id": "1", "t": 5.0, "x": 0.0, "y": -200.0},
        {"type": "fix", "car_id": "1", "t": 7.5, "x": 200.0, "y": 0.0},
    ], tmp_path / "f.jsonl")
    pipe = Pipeline(Fusion(square()))
    pipe.run([feed])
    assert pipe.logical_now == 7.5
