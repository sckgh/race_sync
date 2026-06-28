"""Dev CLI: run recorded feeds through the backbone pipeline.

This is a developer harness, not the operator console. It demonstrates the data path
that exists today — sources -> fusion -> position model + race-state engine — and is the
seed of the replay-based test rig (specs/09 §9.10).

    python -m racesync.cli demo            # synthetic feed through the whole pipeline
    python -m racesync.cli replay FEED.jsonl --track TRACK.geojson
"""

from __future__ import annotations

import argparse
import math
import sys

from .bus import TOPIC_STATE, EventBus
from .fusion import Fusion
from .model import RaceState, TimingEvent, TimingEventKind
from .sources.base import RawFix
from .sources.replay import ReplaySource
from .state_engine import RaceStateEngine
from .track import TrackFrame


def _oval_track(length_target: float = 3896.0, name: str = "demo-oval") -> TrackFrame:
    """A closed oval centreline scaled to ~``length_target`` metres (SMSP-ish for demo).

    Real use loads a surveyed SMSP centreline via ``TrackFrame.from_geojson_line``; this
    is only so ``demo`` runs with no data files.
    """
    pts = []
    n = 64
    a, b = 700.0, 300.0  # semi-axes (m) -> perimeter ~ 3.2 km, scaled below
    for i in range(n):
        th = 2 * math.pi * i / n
        pts.append((a * math.cos(th), b * math.sin(th)))
    frame = TrackFrame(pts, name=name)
    scale = length_target / frame.length
    return TrackFrame([(x * scale, y * scale) for x, y in pts], name=name)


def _demo(args) -> int:
    track = _oval_track()
    bus = EventBus()
    fusion = Fusion(track)
    engine = RaceStateEngine(bus=bus)

    transitions = []
    bus.subscribe(TOPIC_STATE, lambda tr: transitions.append(tr))

    # Two cars lapping the oval at different speeds; print a few sampled positions.
    print(f"track: {track.name}  length={track.length:.0f} m\n")
    engine.arm(t=0.0)
    engine.go_green(t=1.0)
    engine.leader_car = "1"

    speeds = {"1": 55.0, "2": 50.0}  # m/s
    dt = 0.1
    laps_done = {"1": 0, "2": 0}
    for step in range(int(args.seconds / dt)):
        t = 1.0 + step * dt
        for cid, v in speeds.items():
            dist = v * t
            s = (dist / track.length) % 1.0
            x, y, _ = track.point_at(s)
            est = fusion.on_fix(RawFix(car_id=cid, t=t, x=x, y=y, speed=v))
            lap = est.lap_distance.lap
            if lap > laps_done[cid]:
                laps_done[cid] = lap
                engine.on_timing_event(TimingEvent(
                    kind=TimingEventKind.LAP_COMPLETED, t=t, car_id=cid, lap=lap))
        if step % int(2.0 / dt) == 0:
            order = fusion.order()
            lead = fusion.latest(order[0])
            print(f"t={t:6.1f}s  state={engine.state.value:11s}  "
                  f"order={order}  leader_lap={engine.leader_lap}  "
                  f"lead_s={lead.lap_distance.s:.3f}")

        # Demonstrate a Code 60 window mid-run.
        if abs(t - 5.0) < dt / 2:
            engine.set_code60(True, t=t)
            print(f"  >> t={t:.1f}s SAFETY CAR -> CODE 60")
        if abs(t - 9.0) < dt / 2:
            engine.set_code60(False, t=t)
            print(f"  >> t={t:.1f}s RESTART (green)")

    print(f"\nstate transitions: {[(tr.from_state.value, tr.to_state.value) for tr in transitions]}")
    print(f"neutralised for {engine.neutralised_seconds():.1f}s")
    return 0


def _replay(args) -> int:
    if args.track:
        track = TrackFrame.from_geojson_line(args.track)
    else:
        track = _oval_track()
    fusion = Fusion(track)
    engine = RaceStateEngine(clock=lambda: 0.0)
    src = ReplaySource(args.feed)
    n_fix = n_timing = 0
    for event in src.stream():
        if isinstance(event, RawFix):
            fusion.on_fix(event)
            n_fix += 1
        elif isinstance(event, TimingEvent):
            fusion.on_timing_event(event)
            engine.on_timing_event(event)
            n_timing += 1
    print(f"replayed {n_fix} fixes, {n_timing} timing events from {src.name}")
    print(f"final order: {fusion.order()}")
    print(f"state: {engine.state.value}  leader={engine.leader_car} lap={engine.leader_lap}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="racesync", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_demo = sub.add_parser("demo", help="run a synthetic feed through the pipeline")
    p_demo.add_argument("--seconds", type=float, default=12.0)
    p_demo.set_defaults(func=_demo)

    p_replay = sub.add_parser("replay", help="replay a recorded JSONL feed")
    p_replay.add_argument("feed", help="path to a JSONL feed file")
    p_replay.add_argument("--track", help="GeoJSON LineString centreline (optional)")
    p_replay.set_defaults(func=_replay)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
