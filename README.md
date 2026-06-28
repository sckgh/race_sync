# RaceSync

![CI](https://github.com/sckgh/race_sync/actions/workflows/ci.yml/badge.svg)

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

The platform-independent **backbone is in place and tested** (115 tests, CI on
Python 3.11–3.13): position model, track projection, pluggable position/timing sources
(NMEA GPS, UDP telemetry, replay, MyLaps stub), fusion, the race-state engine, the event
bus, pipeline, feed recorder, health monitor, **scoring** (combined real/virtual classes,
timed finish), the **operator console**, the **live combined timing + track-map web view**
(the Strategy-3 fallback), the **injection spike harness + Assetto Corsa companion**, and a
**broadcast/demo** path — all runnable off recorded feeds, no live track or simulator
required.

**Open / external:** the live AC injection spike (needs Assetto Corsa, staged and ready),
and real **MyLaps X2** + **Zello `MRA-RMC`** access (need event sign-off). See the delivery
plan, [`specs/10-delivery-plan-and-risks.md`](specs/10-delivery-plan-and-risks.md).

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
  injection/      # Live car injection (C3): adapter + AC client/receiver + latency spike
  console.py      # Operator console (C8): commands + live dashboard
  web.py          # Live combined timing + track-map web view (Strategy-3 fallback / demo)
  viz.py          # Standalone visualizer: render cars on the track to SVG / ASCII
  sources/udp.py  # Car -> RaceSync position uplink (UDP telemetry, specs/12)
  simgen.py       # NMEA 0183 test-data generator (N cars, varying speeds, SMSP-anchored)
  cli.py          # Dev entry point (replay a feed through the pipeline)
tests/            # pytest suite (stdlib-only core, runs anywhere; 115 tests)
examples/nmea/    # generated per-car NMEA + combined timeline (see gen-nmea)
tools/ac_companion/  # Assetto Corsa app: receives phantoms, draws overlay (for when AC is open)
.github/workflows/   # CI: tests on py3.11-3.13 + lint + CLI smoke
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
python -m racesync.cli broadcast                          # live web view -> http://127.0.0.1:8013
python -m racesync.cli gen-nmea --cars 10 --rate 10 --duration 60  # NMEA 0183 test data
python -m racesync.cli spike --nmea-dir examples/nmea       # spike on the 10-car NMEA field
python -m racesync.cli visualize --nmea-dir examples/nmea --out cars.svg  # see the cars
```

### When you have Assetto Corsa open

Install the companion app (`tools/ac_companion/`, see its README), then stream the field at
it: `python -m racesync.cli spike --nmea-dir examples/nmea --use-ac`. The overlay shows the
real field moving inside AC. (It visualizes phantoms; it does not yet move collidable cars —
that's the open Phase-1 spike, see `specs/05`.)

## Quick start (dev)

```bash
python -m pip install -e ".[dev]"
pytest
python -m racesync.cli --help
```

The core has **no third-party dependencies**; only the test runner and, later,
adapter-specific extras do.
