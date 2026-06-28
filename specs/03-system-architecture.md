# 03 — System Architecture

## 3.1 Overview

RaceSync sits between three external worlds — the **real race** (timing, GPS, race
control, Zello), the **simulator** (hosting the virtual field), and the **operator** — and
keeps them in sync. The design goal is a small number of clearly-bounded components joined
by a single internal event model, so that any one external dependency can be swapped or can
fail without collapsing the whole.

```
        REAL RACE WORLD                 RaceSync CORE                   VIRTUAL WORLD
  ┌───────────────────────┐      ┌────────────────────────┐      ┌───────────────────────┐
  │ MyLaps X2 timing feed  │────▶ │  Feed Ingestion        │      │  Sim Injection Adapter │────▶ Simulator
  │ (passings, laps, secs) │      │   ↳ normalises to the  │────▶ │   ↳ phantom cars        │      (hosts ≤24
  │ In-car GPS (optional)  │────▶ │     Position Model     │      │     driven by positions │      virtual drivers)
  └───────────────────────┘      │                        │      └───────────────────────┘
                                  │  Race State Engine      │────▶ ┌───────────────────────┐
  ┌───────────────────────┐      │   ↳ flags, SC→Code 60,  │      │  Sim Telemetry Reader  │◀──── Simulator
  │ Race Control (official) │◀──▶ │     leader laps,        │◀─────│   ↳ virtual lap/timing  │      (read-only SDK)
  └───────────────────────┘      │     timed finish        │      └───────────────────────┘
                                  │                        │
  ┌───────────────────────┐      │  Scoring & Results      │────▶  Combined timing / results (#08)
  │ Zello MRA-RMC (1-way)  │────▶ │  Audio Bridge           │────▶ Virtual drivers' audio (#07)
  └───────────────────────┘      └───────────┬────────────┘
                                              │
                                  ┌───────────▼────────────┐
                                  │  Operator Console       │  (trigger Code 60, fire chequer,
                                  │  + Sync Health Monitor  │   monitor health, manual overrides)
                                  └────────────────────────┘
```

## 3.2 Components

### C1 — Feed Ingestion
Connects to the real-race position/timing sources and normalises every input into the
internal **Position Model** and a stream of **timing events** (passings, lap completions,
sector times, leader changes). Source-specific adapters (MyLaps X2, GPS) sit behind one
interface so the rest of the system is source-agnostic. Detailed in [`04-data-feeds.md`](04-data-feeds.md).

**Responsibilities:** connection management, reconnection/backfill, clock alignment,
dead-reckoning during dropouts, per-car identity resolution (transponder / MyLaps Driver
ID), quality flags on each position estimate.

### C2 — Race State Engine
The single source of truth for **shared race state**: global flag/neutralisation state
(green / Safety Car↔Code 60 / chequered), the **real leader's lap count and race
completion**, the CPS window (informational), and session phase (formation, racing,
finished). It consumes timing events (C1) and operator actions (C8), and emits state
transitions that the Sim Injection Adapter, Audio Bridge, Scoring, and Console all react
to. Detailed in [`06-race-state-sync.md`](06-race-state-sync.md).

### C3 — Sim Injection Adapter
Pushes the real field into the simulator as **phantom cars** positioned from the Position
Model, and applies global state (e.g. forces virtual Code 60 behaviour where the platform
allows). This is the **highest-risk component** and its very feasibility — plus the choice
of simulator — is the subject of [`05-sim-injection-feasibility.md`](05-sim-injection-feasibility.md).
Implemented behind an interface so the platform can change without touching C1/C2.

### C4 — Sim Telemetry Reader
Reads the virtual field's live state from the sim's (read-only) SDK / shared memory:
virtual car positions, lap and sector times, pit events. Feeds Scoring (C6) and the Sync
Health Monitor. Every mainstream sim supports this; it is low-risk and platform-specific
only at the edges.

### C5 — Audio Bridge
Relays the one-way Zello **`MRA-RMC`** channel into virtual drivers' audio. Detailed in
[`07-audio-race-management.md`](07-audio-race-management.md).

### C6 — Scoring & Results
Combines real timing (authoritative, from C1/official) and virtual timing (from C4) into
one classification with **separate real/virtual classes** and a **timed virtual finish**.
Detailed in [`08-scoring-and-classification.md`](08-scoring-and-classification.md).

### C7 — Sync Health Monitor
Continuously compares expectations vs reality (feed freshness, injection lag, audio delay,
state divergence) and surfaces health + alarms to the operator. Defines the degraded-mode
triggers in [`09-non-functional-requirements.md`](09-non-functional-requirements.md).

### C8 — Operator Console
The human control surface: **trigger/clear Code 60**, **fire the virtual chequer** (or
confirm the automatic one), see sync health, and invoke **manual overrides** (pause
injection, freeze virtual field, drop a misbehaving phantom). One operator, one screen.

## 3.3 Internal event model

All components communicate through a single internal **event bus / state store** rather
than point-to-point. Core message families:

| Family | Examples | Producer → Consumers |
|--------|----------|----------------------|
| `position.update` | `{carId, t, x, y, [lat,lon], speed, heading, quality}` | C1 → C3, C7 |
| `timing.event` | `passing`, `lap_completed{carId, lap}`, `sector`, `leader_changed`, `race_completed` | C1 → C2, C6 |
| `state.transition` | `green`, `safety_car_on/off`→`code60_on/off`, `chequered`, `phase_changed` | C2 → C3, C5, C6, C8 |
| `sim.telemetry` | virtual `lap_completed`, `position`, `pit` | C4 → C6, C7 |
| `operator.command` | `code60_set`, `fire_chequer`, `override.*` | C8 → C2, C3 |
| `health.*` | freshness, lag, divergence, alarms | C7 → C8 |

Benefits: each external integration is isolated; the bus is the natural place for logging,
replay, and the audit trail (#08, #09); components can be developed and tested against
recorded event streams.

## 3.4 Deployment topology

A hybrid edge/cloud layout reflecting where each dependency lives:

```
  ┌──────────────── TRACKSIDE (SMSP) ────────────────┐     ┌──────────── CLOUD / RELAY ───────────┐
  │  Edge node (operator laptop/server):              │     │  Sim host(s): dedicated server +      │
  │   • Feed Ingestion (C1) — near MyLaps/GPS source  │◀───▶│    Sim Injection (C3), Telemetry (C4) │
  │   • Race State Engine (C2)                         │     │  Audio relay (C5) ingress             │
  │   • Operator Console (C8) + Health (C7)            │     │  Scoring/Results service (C6)         │
  │   • Local buffer/audit log                         │     │  Combined timing web view (#08)       │
  └───────────────────────────────────────────────────┘     └───────────────────────────────────────┘
            ▲                                                          ▲
            │ Zello MRA-RMC (C5 source)                                │ remote virtual drivers (≤24)
            └────────────────────────────────────── internet ─────────┘
```

- **Trackside edge node** runs the components that must keep working through internet
  blips and that sit closest to the timing/GPS source. It keeps a local buffer and the
  authoritative audit log.
- **Cloud/relay** hosts the simulator server, scoring service, and public/combined timing
  view, where remote virtual drivers connect.
- **Split-brain rule:** if the edge↔cloud link drops, the **Race State Engine on the edge
  remains authoritative**; the cloud side holds last-known state and the operator is
  alarmed. No automatic green/Code 60 changes happen blind. (#09)

> The exact split (e.g. running C2 trackside vs co-located with the sim) is a deployment
> decision to validate in the spikes; the component boundaries above make either layout
> possible.

## 3.5 Latency budget (allocation; targets in #09)

End-to-end "real car moves → virtual driver sees it move" is the sum of: feed acquisition
(C1) + normalisation/dead-reckoning + edge→sim transport + injection apply (C3) + sim
render. The budget is allocated and measured per hop by the Health Monitor (C7); #09 sets
the numeric targets and the degraded-mode thresholds. **The feasibility spike (#05) must
measure the C3 + transport hops specifically**, as they dominate and are the least certain.

## 3.6 Technology posture (non-binding)

- **Language/runtime:** not fixed here. C1/C2/C3 favour a low-latency, well-supported
  runtime with good UDP/binary-protocol and game-SDK bindings (the sim SDKs are typically
  C/C++ with community bindings in C#/Python/Rust). The injection adapter's language is
  effectively dictated by the chosen sim's plugin/SDK (see #05).
- **Transport:** internal bus can be lightweight (in-process + a message broker for the
  edge↔cloud hop). Position streams favour UDP-style transport with sequence numbers over
  guaranteed-ordered TCP, given freshness beats completeness.
- **Persistence:** append-only event log for audit/replay; results store for scoring.
- These are revisited once #05 fixes the platform; nothing above pre-commits the stack.

## 3.7 Interfaces summary

| Boundary | Direction | Protocol (candidate) | Spec |
|----------|-----------|----------------------|------|
| MyLaps X2 → C1 | in | X2 timing data feed (TBC-2) | #04 |
| GPS units → C1 | in | UDP/serial/MQTT lat-lon stream | #04 |
| C3 → Simulator | out | sim-specific plugin / server API | #05 |
| Simulator → C4 | in | sim SDK / shared memory (read-only) | #05 |
| Zello MRA-RMC → C5 | in | Zello channel relay | #07 |
| C6 → results consumers | out | web view / export | #08 |
| C8 ↔ C2/C3 | both | internal bus | this doc |
