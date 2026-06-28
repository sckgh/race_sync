# RaceSync

Sync GPS/timing data from real race cars into a racing simulator, run a remote virtual
field alongside the physical field as its own class, bridge race-management audio, and
score both together under one race.

Reference event: the **Viola Private Wealth Sydney 300** — 300 km / 77 laps at Sydney
Motorsport Park.

> **Specs first.** The design lives in [`specs/`](specs/) — start with
> [`specs/README.md`](specs/README.md). Read [`specs/05-sim-injection-feasibility.md`](specs/05-sim-injection-feasibility.md)
> for the project's central risk, and [`specs/11-gps-hardware-options.md`](specs/11-gps-hardware-options.md)
> for the position-hardware recommendations.

## Status

Early development. The platform-independent **backbone** is being built first (per the
delivery plan, [`specs/10-delivery-plan-and-risks.md`](specs/10-delivery-plan-and-risks.md)):
position model, track projection, pluggable position/timing sources, the race-state
engine, and an in-process event bus — all testable off recorded feeds, without a live
track or simulator.

## Layout

```
src/racesync/
  model.py        # Core types: PositionEstimate, TimingEvent, RaceState, ...
  bus.py          # In-process pub/sub event bus
  track.py        # TrackFrame: geodetic -> distance-along-track (s) + x/y, map-matching
  sources/        # Pluggable inputs (PositionSource): NMEA GPS, replay, MyLaps stub
  fusion.py       # Fuse sources + dead-reckon into one Position Model stream
  state_engine.py # Shared race state machine (GREEN / CODE 60 / timed finish)
  runner.py       # Pipeline: timestamp-ordered merge of sources -> fusion -> state -> bus
  recording.py    # FeedRecorder: capture raw feeds to JSONL (inverse of replay)
  health.py       # HealthMonitor (C7): feed freshness/rate, GO/DEGRADED/FAULT, alarms
  scoring.py      # Scoring (C6): separate real/virtual classes, timed finish, penalties
  injection/      # Live car injection (C3): SimInjectionAdapter, AC stub, latency spike
  console.py      # Operator console (C8): commands + live dashboard
  sources/udp.py  # Car -> RaceSync position uplink (UDP telemetry, specs/12)
  simgen.py       # NMEA 0183 test-data generator (N cars, varying speeds, SMSP-anchored)
  cli.py          # Dev entry point (replay a feed through the pipeline)
tests/            # pytest suite (stdlib-only core, runs anywhere; 92 tests)
examples/nmea/    # generated per-car NMEA + combined timeline (see gen-nmea)
examples/         # sample_feed.jsonl — a ready-to-replay recorded feed
specs/            # Design documents
```

## Try it

```bash
python -m racesync.cli demo                       # synthetic feed through the pipeline
python -m racesync.cli replay examples/sample_feed.jsonl   # replay a recorded feed
python -m racesync.cli replay examples/sample_feed.jsonl --record out.jsonl  # capture parity
python -m racesync.cli spike examples/sample_feed.jsonl    # injection latency spike (offline)
python -m racesync.cli console                             # operator console (scripted demo)
python -m racesync.cli console --interactive              # operator console (REPL)
python -m racesync.cli gen-nmea --cars 10 --rate 10 --duration 60  # NMEA 0183 test data
```

## Quick start (dev)

```bash
python -m pip install -e ".[dev]"
pytest
python -m racesync.cli --help
```

The core has **no third-party dependencies**; only the test runner and, later,
adapter-specific extras do.
