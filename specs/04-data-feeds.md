# 04 — Data Feeds: Position & Timing

The quality of the whole concept is capped by how well RaceSync knows **where each real car
is, right now**. This document specifies the two candidate input sources, the internal
**Position Model** they both feed, and how the system degrades when data is coarse or
missing. The position source is **not yet fixed**, so both paths are first-class and
pluggable behind one interface.

## 4.1 The two sources

### Source A — MyLaps X2 timing feed

**What it is:** transponder detections at fixed track loops, yielding *passings* and, from
them, lap and sector times, plus the order of cars. The event already mandates MyLaps
transponders (Art. 13.1) and may use MyLaps Driver ID (Art. 6.1).

**What it gives us:**
- High-accuracy **timing** (lap/sector times to ms; loop crossings).
- Car **order** and **leader** with confidence.
- Position only **discretely** — we know a car crossed loop *L* at time *t*, not where it is
  between loops.

**What it does NOT give us:** continuous position. Between two loops a car's location must
be **interpolated/dead-reckoned** along the known track centreline using elapsed time and
expected pace.

**Access:** depends on whether a live X2 data feed is exposed to RaceSync at the event
(**TBC-2**, #02). This must be confirmed; some events restrict the live feed to accredited
timing providers. Fallback if no live feed: scrape the public live-timing view (lower rate,
higher risk — see #10 O-3).

**Spatial resolution** is set by **loop count**. With only start/finish + a few sector
loops, between-loop interpolation spans hundreds of metres — fine for an order-accurate
*leaderboard*, marginal for *visual injection* where drivers expect cars in roughly the
right spot. Number/placement of loops at SMSP is **TBC**.

### Source B — True GPS (lat/lon stream)

**What it is:** an in-car GPS (or GNSS) unit emitting continuous position, ideally with
speed and heading, at a useful rate.

**What it gives us:**
- **Continuous position** — the thing visual injection actually needs.
- Speed/heading to drive plausible motion and dead-reckoning.

**What it does NOT give us for free:**
- **Timing-grade lap data** — GPS lap detection is derived (crossing a virtual finish line)
  and less authoritative than transponder timing. So even with GPS, **official lap counts
  and the leader still come from MyLaps** (#01 A2).
- **Accuracy/rate guarantees** — consumer GPS at 1 Hz with 2–5 m error is too coarse/slow
  for 200 km/h cars (≈55 m travelled per second). Usable injection wants **≥10 Hz** and
  sub-2 m accuracy (RTK-corrected GNSS reaches cm-level). Whether such units are fitted is
  **TBC-3** (#02).

**Concrete unit options** (rate, RTK, accuracy, pricing, corrections & telemetry
architecture, fleet cost) are in [`11-gps-hardware-options.md`](11-gps-hardware-options.md).

**Note on "MyLaps GPS":** the brief mentions MyLaps GPS. MyLaps' ecosystem is primarily
transponder/loop timing; any GPS capability and its rate/accuracy must be verified against
the actual hardware in use (**TBC-3**). The spec deliberately treats GPS as a generic
GNSS source so a different unit (e.g. a dedicated RTK logger) can be substituted.

### Source comparison

| Property | A — MyLaps X2 timing | B — True GPS |
|----------|----------------------|--------------|
| Continuous position | ✗ (interpolated) | ✓ |
| Timing accuracy | ✓ authoritative | ✗ derived |
| Update rate | per loop crossing | configurable (target ≥10 Hz) |
| Spatial accuracy | loop-bounded | unit-dependent (m → cm w/ RTK) |
| Availability at event | likely, feed access TBC | only if units fitted (TBC) |
| Best for | leaderboard, order, official laps | **visual injection** |

### Recommendation

Treat the sources as **complementary, fused**, not either/or:

- **Use MyLaps timing as the authoritative skeleton** — official laps, sectors, order,
  leader, race completion. RaceSync never overrides official timing with GPS.
- **Use GPS (where available) for continuous position** to drive injection fidelity.
- **Fuse:** snap/anchor GPS to the track and correct it at each loop crossing (the loop
  gives a known position+time that re-anchors the GPS/dead-reckoning estimate).
- **Degrade gracefully:** with timing only, injection runs on **interpolated** position
  (lower fidelity but still order-correct); with GPS only, timing is **derived** and clearly
  marked unofficial until reconciled with MyLaps.

The **minimum viable** path for the leaderboard and state sync is **Source A alone**. The
**high-fidelity injection** experience wants **Source B**. The feasibility spike (#05) must
test injection against *both* a real/representative GPS trace and a timing-only trace.

## 4.2 The Position Model (internal)

One normalised representation all consumers use, independent of source.

### Per-car position estimate
```
PositionEstimate {
  carId            // stable id keyed to transponder / MyLaps id
  t                // timestamp on RaceSync's aligned clock
  s                // distance along track centreline (lap fraction 0..1 + lap no.)
  x, y             // track-plane coordinates (projected), for injection
  lat, lon         // original geodetic, when from GPS
  speed, heading   // measured (GPS) or estimated (interpolated)
  source           // GPS | TIMING_INTERP | FUSED | DEAD_RECKONED
  quality          // 0..1 confidence + staleness age
}
```

- **Track frame:** a surveyed centreline + width model for the confirmed SMSP config
  (TBC-1) lets us express position as **distance-along-track `s`** (robust, what timing
  naturally gives) and convert to **x/y** for the sim. GPS is projected into the same frame
  and **map-matched** (snapped) to the track.
- **Lap-relative `s`** is the lingua franca between timing (loop = known `s`) and GPS
  (continuous `s` after map-matching), which makes fusion tractable.

### Clock alignment
All sources are timestamped onto **one aligned clock**. Loop crossings (precise times) and
GPS timestamps are reconciled to a common reference so position and timing agree. Drift and
offset handling is a Health Monitor concern (#07/C7).

### Identity resolution
- **Car identity** ← transponder / MyLaps id (stable across the event).
- **Driver identity** (multi-driver cars) ← MyLaps Driver ID where present, else the
  SMS-nominated driver (Art. 6.2). Driver changes update the model but do not change `carId`.

## 4.3 Dropout & data-quality handling

Real feeds are lossy; the regs even codify a 3-lap transponder-failure tolerance
(Art. 13.2). RaceSync must behave predictably when data is thin:

| Situation | Behaviour |
|-----------|-----------|
| GPS gap (< few s) | **Dead-reckon** from last speed/heading along centreline; mark `quality` decaying; injected car keeps moving plausibly. |
| GPS gap (longer) / no GPS | Fall back to **timing interpolation** between loops; injected car advances at expected pace. |
| Timing gap (missed loop) | Hold order; widen position uncertainty; reconcile at next crossing. |
| Total loss for a car (toward the 3-lap rule) | Injected car **visibly degrades** (e.g. ghosted/greyed) then is **parked/removed** rather than teleporting wildly; operator alerted. |
| Out-of-order / duplicate packets | Sequence-number + timestamp ordering; drop stale. |
| Reconnect | Backfill from buffer where the source supports it; otherwise resync to live and flag the gap in the audit log. |

**Principle:** *plausible and stable* beats *precise but jumpy*. A phantom car must never
teleport or strobe in front of virtual drivers; uncertainty is expressed as smoothed motion
and visual degradation, not jitter.

## 4.4 Ingestion interface (so sources are swappable)

```
interface PositionSource {
  connect(config) -> stream
  // emits PositionEstimate and/or TimingEvent
  onPosition(cb)        // continuous (GPS) or interpolated
  onTimingEvent(cb)     // passing | lap_completed | sector | leader_changed | race_completed
  health() -> {connected, lastPacketAge, rate, dropRate}
}
```

Concrete adapters: `MyLapsX2Source`, `GpsUdpSource` (+ a `ReplaySource` that plays recorded
feeds for testing). The Fusion layer subscribes to one or more sources and emits the unified
Position Model + timing stream onto the bus (#03). The rest of RaceSync depends only on the
unified model — **swapping or losing a source changes fidelity, not correctness.**

## 4.5 Requirements

- **F-04-1** The system MUST ingest MyLaps X2 timing (passings, lap/sector times, order,
  leader) when a feed is available, and treat it as authoritative for laps/order.
- **F-04-2** The system MUST ingest a continuous GPS lat/lon stream when available and
  map-match it to the track frame.
- **F-04-3** The system MUST operate with **either source alone**, at reduced fidelity,
  without code changes (config only).
- **F-04-4** The system MUST fuse sources when both are present, re-anchoring GPS/dead-
  reckoning at each loop crossing.
- **F-04-5** The system MUST dead-reckon through short gaps and **degrade visibly** through
  long ones, never producing teleports/jitter in injected cars.
- **F-04-6** The system MUST stamp every estimate with `source` and `quality` and expose
  feed health to the Monitor and Console.
- **F-04-7** The system MUST resolve car identity from transponder/MyLaps id and driver
  identity from MyLaps Driver ID / SMS nomination, tracking driver changes.
- **F-04-8** The system SHOULD record all raw feeds to enable replay-based testing and the
  audit trail.

## 4.6 Open items (to #10)

- **TBC-2** X2 live feed access and protocol details.
- **TBC-3** GPS hardware: presence, rate, accuracy, transport.
- **TBC-1** Confirmed SMSP config → survey data for the track frame.
- **O-3** Acceptability of public live-timing scraping as a fallback.
