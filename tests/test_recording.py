from racesync.fusion import Fusion
from racesync.model import TimingEvent, TimingEventKind
from racesync.recording import FeedRecorder, to_record
from racesync.runner import Pipeline
from racesync.sources.base import RawFix
from racesync.sources.replay import ReplaySource
from racesync.track import TrackFrame


def square(side=400.0):
    h = side / 2
    # Include a geodetic reference so geodetic (lat/lon) fixes can be map-matched.
    return TrackFrame([(-h, -h), (h, -h), (h, h), (-h, h)], ref=(-33.8, 150.87))


def test_to_record_omits_none_keys():
    rec = to_record(RawFix(car_id="1", t=0.0, x=1.0, y=2.0))
    assert rec == {"type": "fix", "car_id": "1", "t": 0.0, "x": 1.0, "y": 2.0, "quality": 1.0}
    assert "lat" not in rec


def test_timing_record_round_trips():
    ev = TimingEvent(TimingEventKind.LAP_COMPLETED, t=95.0, car_id="1", lap=1, value=94.0)
    rec = to_record(ev)
    assert rec["kind"] == "lap_completed"
    assert rec["value"] == 94.0


def test_capture_then_replay_parity(tmp_path):
    """Recording raw inputs then replaying them must reproduce the same events."""
    original = [
        {"type": "fix", "car_id": "1", "t": 0.0, "x": 0.0, "y": -200.0, "speed": 50.0},
        {"type": "fix", "car_id": "2", "t": 0.1, "lat": -33.8, "lon": 150.87, "quality": 0.8},
        {"type": "timing", "kind": "lap_completed", "t": 95.0, "car_id": "1", "lap": 1},
    ]
    src = ReplaySource.from_records(original, tmp_path / "in.jsonl")

    out = tmp_path / "captured.jsonl"
    with FeedRecorder(out) as rec:
        pipe = Pipeline(Fusion(square()), recorder=rec)
        pipe.run([src])
    assert rec.count == 3

    # Replay the captured file; events must match the originals in order/type/values.
    replayed = list(ReplaySource(out).stream())
    assert len(replayed) == 3
    assert isinstance(replayed[0], RawFix) and replayed[0].speed == 50.0
    assert isinstance(replayed[1], RawFix) and replayed[1].lat == -33.8
    assert isinstance(replayed[2], TimingEvent) and replayed[2].lap == 1
