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
from .console import OperatorConsole
from .fusion import Fusion
from .health import HealthMonitor
from .model import RaceState, TimingEvent, TimingEventKind
from .injection import InjectionHarness, LoopbackAdapter
from .injection.assetto_corsa import AssettoCorsaAdapter
from .recording import FeedRecorder
from .runner import Pipeline
from .scoring import CarClass, Entry, ScoringService, format_classification
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
    """A short hybrid race through the whole stack: pipeline, state, scoring, health."""
    track = _oval_track()
    bus = EventBus()
    fusion = Fusion(track)
    engine = RaceStateEngine(bus=bus)
    health = HealthMonitor(bus=bus, state_engine=engine)
    health.register("synthetic", fresh=0.5, fault=2.0)
    scoring = ScoringService(state_engine=engine)
    scoring.attach(bus)
    pipe = Pipeline(fusion, state_engine=engine, bus=bus, health=health)

    # Field: two real cars (with MA divisions) and two virtual cars (own class).
    scoring.register(Entry("1", "1", CarClass.REAL, "A. Fast", "B"))
    scoring.register(Entry("2", "2", CarClass.REAL, "B. Steady", "C"))
    scoring.register(Entry("V1", "V1", CarClass.VIRTUAL, "S. Remote"))
    scoring.register(Entry("V2", "V2", CarClass.VIRTUAL, "T. Remote"))
    speeds = {"1": 56.0, "2": 52.0, "V1": 55.0, "V2": 50.0}

    print(f"track: {track.name}  length={track.length:.0f} m\n")
    engine.arm(t=0.0)
    engine.go_green(t=1.0)
    engine.leader_car = "1"

    dt = 0.1
    laps_done = {c: 0 for c in speeds}
    finished = False
    for step in range(int(args.seconds / dt)):
        t = 1.0 + step * dt
        for cid, v in speeds.items():
            s = (v * t / track.length) % 1.0
            x, y, _ = track.point_at(s)
            est = pipe.feed(RawFix(car_id=cid, t=t, x=x, y=y, speed=v), "synthetic")
            lap = est.lap_distance.lap
            if lap > laps_done[cid]:
                laps_done[cid] = lap
                lap_time = track.length / v
                pipe.feed(TimingEvent(TimingEventKind.LAP_COMPLETED, t=t, car_id=cid,
                                      lap=lap, value=lap_time), "synthetic")

        if step % int(2.0 / dt) == 0:
            order = fusion.order()
            print(f"t={t:6.1f}s  state={engine.state.value:11s}  "
                  f"order={order}  leader_lap={engine.leader_lap}")

        if abs(t - 5.0) < dt / 2:
            engine.set_code60(True, t=t)
            scoring.add_penalty("V2", laps=0, seconds=5.0, reason="overtake under Code 60")
            print(f"  >> t={t:.1f}s SAFETY CAR -> CODE 60 (virtual field neutralised)")
        if abs(t - 9.0) < dt / 2:
            engine.set_code60(False, t=t)
            print(f"  >> t={t:.1f}s RESTART (green)")

        # Timed finish: when the real leader completes the (demo) distance of 2 laps,
        # the virtual field is chequered wherever it is on track.
        if not finished and engine.leader_lap >= 2:
            engine.arm_finish(t=t, car_id="1")
            engine.fire_chequer(t=t)
            scoring.finalize(t=t)
            finished = True
            print(f"  >> t={t:.1f}s CHEQUERED FLAG (real leader completed distance)")
            break

    snap = health.tick(now=pipe.logical_now)
    print(f"\nneutralised for {engine.neutralised_seconds():.1f}s   health={snap.overall.value}\n")
    combined = scoring.combined()
    for klass in (CarClass.REAL, CarClass.VIRTUAL):
        print(format_classification(combined[klass]))
        print()
    return 0


def _replay(args) -> int:
    track = TrackFrame.from_geojson_line(args.track) if args.track else _oval_track()
    bus = EventBus()
    fusion = Fusion(track)
    engine = RaceStateEngine(bus=bus)
    health = HealthMonitor(bus=bus, state_engine=engine)
    health.register("timing", fresh=120.0, fault=300.0)
    src = ReplaySource(args.feed)

    recorder = FeedRecorder(args.record) if args.record else None
    if recorder:
        recorder.open()
    try:
        pipe = Pipeline(fusion, state_engine=engine, bus=bus, recorder=recorder, health=health)
        counts = pipe.run([src])
    finally:
        if recorder:
            recorder.close()

    snap = health.tick(now=pipe.logical_now)
    print(f"replayed {counts['fix']} fixes, {counts['timing']} timing events from {src.name}")
    print(f"final order: {fusion.order()}")
    print(f"state: {engine.state.value}  leader={engine.leader_car} lap={engine.leader_lap}")
    print(f"health: {snap.overall.value}  alarms={snap.alarms or 'none'}")
    if recorder:
        print(f"recorded {recorder.count} raw events -> {args.record}")
    return 0


def _spike(args) -> int:
    """Phase-1 injection spike: drive a feed's positions into a sim adapter, measure latency.

    This is the OFFLINE simulation mode (specs/05 §5.4): replay timestamps are logical, so
    latency is modelled (``--sim-latency`` base + small deterministic jitter) to exercise
    the measurement + scoring machinery. A LIVE spike swaps the loopback adapter for the AC
    adapter, feeds real captured timestamps, and lets the harness time the clock directly.
    """
    track = TrackFrame.from_geojson_line(args.track) if args.track else _oval_track()
    fusion = Fusion(track)

    if args.use_ac:
        adapter = AssettoCorsaAdapter(host=args.ac_host, port=args.ac_port)
        print(f"target: Assetto Corsa companion at {args.ac_host}:{args.ac_port} "
              f"(UDP send only — does NOT prove AC renders the car; see specs/05)")
    else:
        adapter = LoopbackAdapter()
        print("target: loopback adapter (in-memory)")
    adapter.connect()

    # Build the position estimates from the feed via fusion.
    estimates = []
    for event in ReplaySource(args.feed).stream():
        if isinstance(event, RawFix):
            estimates.append(fusion.on_fix(event))
        elif isinstance(event, TimingEvent):
            fusion.on_timing_event(event)

    harness = InjectionHarness(adapter)
    base = args.sim_latency
    report = harness.run(estimates, latency_model=lambda i, e: base + (i % 5) * 0.01)
    adapter.close()

    print(f"phantoms injected: {adapter.health().get('phantoms', len(adapter.spawned))}  "
          f"from {len(estimates)} position estimates\n")
    print(report)
    print("\n(offline simulation — modelled latency. Run a LIVE spike with real timestamps "
          "and an AC companion to get a real verdict; see specs/05 §5.4.)")
    return 0


def _console(args) -> int:
    """Launch the operator console. Interactive REPL, or a scripted demo by default."""
    bus = EventBus()
    engine = RaceStateEngine(bus=bus)
    health = HealthMonitor(bus=bus, state_engine=engine)
    scoring = ScoringService(state_engine=engine)
    scoring.attach(bus)
    scoring.register(Entry("1", "1", CarClass.REAL, "A. Fast", "B"))
    scoring.register(Entry("2", "2", CarClass.REAL, "B. Steady", "C"))
    scoring.register(Entry("V1", "V1", CarClass.VIRTUAL, "S. Remote"))
    scoring.register(Entry("V2", "V2", CarClass.VIRTUAL, "T. Remote"))
    adapter = LoopbackAdapter(); adapter.connect()

    # Seed some classification data so the dashboard is not empty.
    for cid, lap in (("1", 12), ("2", 11), ("V1", 11), ("V2", 10)):
        engine.leader_car = "1"
        scoring.on_timing_event(TimingEvent(TimingEventKind.LAP_COMPLETED, t=0.0,
                                            car_id=cid, lap=lap, value=99.0 + lap * 0.01))

    console = OperatorConsole(engine, health, scoring, adapter=adapter, clock=lambda: 0.0)

    if args.interactive:
        console.run()
        return 0

    # Scripted demonstration (no TTY needed): run a sequence and show the dashboard.
    for cmd in ("arm", "green", "code60 on", "penalty V2 1 overtake under code60",
                "code60 off", "chequer force"):
        res = console.dispatch(cmd)
        print(f"racesync> {cmd}\n  -> {res.message.splitlines()[0] if res.message else 'ok'}\n")
    print(console.render())
    return 0


def _gen_nmea(args) -> int:
    """Generate NMEA 0183 test data for a field of cars (specs/11, specs/12)."""
    from pathlib import Path

    from .simgen import default_field, make_smsp_track, sample_to_nmea, simulate

    track = make_smsp_track()
    cars = default_field(args.cars, base=args.base_speed)
    samples = simulate(track, cars, rate_hz=args.rate, duration_s=args.duration)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Per-car NMEA files (what each receiver would emit).
    per_car: dict[str, list[str]] = {c.car_id: [] for c in cars}
    combined: list[str] = []
    for s in samples:
        g, r = sample_to_nmea(s)
        per_car[s.car_id].extend((g, r))
        combined.append(f"{s.t:.3f} {s.car_id} {g}")
        combined.append(f"{s.t:.3f} {s.car_id} {r}")
    for cid, lines in per_car.items():
        (out / f"car_{cid}.nmea").write_text("\n".join(lines) + "\n")
    (out / "combined.timeline.txt").write_text("\n".join(combined) + "\n")

    print(f"track: {track.name}  length={track.length:.0f} m  "
          f"ref=({track.ref[0]:.5f},{track.ref[1]:.5f})")
    print(f"cars: {len(cars)} @ {args.rate:g} Hz for {args.duration:g}s "
          f"(speeds {cars[0].base_speed:.0f}-{cars[-1].base_speed:.0f} m/s = "
          f"{cars[0].base_speed*3.6:.0f}-{cars[-1].base_speed*3.6:.0f} km/h)")
    print(f"wrote {len(cars)} per-car .nmea files + combined.timeline.txt to {out}/\n")
    print("sample (car_01, first GGA + RMC):")
    g, r = sample_to_nmea(samples[0] if samples[0].car_id == "01" else
                          next(s for s in samples if s.car_id == "01"))
    print(f"  {g}\n  {r}")
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
    p_replay.add_argument("--record", help="capture raw events to a JSONL file (parity check)")
    p_replay.set_defaults(func=_replay)

    p_spike = sub.add_parser("spike", help="run the injection latency spike on a feed")
    p_spike.add_argument("feed", help="path to a JSONL feed file")
    p_spike.add_argument("--track", help="GeoJSON LineString centreline (optional)")
    p_spike.add_argument("--sim-latency", type=float, default=0.08,
                         help="modelled base injection latency in seconds (offline mode)")
    p_spike.add_argument("--use-ac", action="store_true",
                         help="send to an Assetto Corsa companion over UDP instead of loopback")
    p_spike.add_argument("--ac-host", default="127.0.0.1")
    p_spike.add_argument("--ac-port", type=int, default=9013)
    p_spike.set_defaults(func=_spike)

    p_console = sub.add_parser("console", help="operator console (state, health, scoring)")
    p_console.add_argument("--interactive", action="store_true",
                           help="drop into the interactive command REPL")
    p_console.set_defaults(func=_console)

    p_gen = sub.add_parser("gen-nmea", help="generate NMEA 0183 test data for N cars")
    p_gen.add_argument("--cars", type=int, default=10)
    p_gen.add_argument("--rate", type=float, default=10.0, help="samples/sec per car (Hz)")
    p_gen.add_argument("--duration", type=float, default=60.0, help="seconds")
    p_gen.add_argument("--base-speed", type=float, default=45.0, help="slowest car m/s")
    p_gen.add_argument("--out", default="examples/nmea", help="output directory")
    p_gen.set_defaults(func=_gen_nmea)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
