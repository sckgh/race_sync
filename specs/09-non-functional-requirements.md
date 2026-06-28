# 09 — Non-Functional Requirements

Cross-cutting qualities that make RaceSync usable at a live, sanctioned event. Numeric
targets are **initial design targets**, to be validated and tuned by the #05 feasibility
spike and trackside testing; they are stated so the system can be measured against them.

## 9.1 Latency

End-to-end "real car moves → virtual driver sees it" is the headline number. Budget is
allocated per hop (#03 §3.5) and measured continuously by the Health Monitor (C7).

| Path | Target (typical) | Degraded threshold | Notes |
|------|------------------|--------------------|-------|
| Position: real car → virtual screen | **≤ 250 ms** | > 500 ms sustained | Dominated by feed + injection + transport; the #05 spike must measure this. |
| State transition (GREEN / CODE 60 / CHEQUERED) → both fields | **≤ 1 s** | > 3 s | No field may race green while the other is neutralised beyond this. |
| `MRA-RMC` voice relay → virtual drivers | **≤ 2 s** | > 5 s | Informational; intelligibility > latency. |
| CODE 60 **machine cue** → virtual drivers | **≤ 500 ms** | > 1 s | Sourced from state engine, not the voice path (#07). |
| Operator action (e.g. Code 60) → effect | **≤ 1 s** | > 2 s | Human-in-the-loop must feel responsive. |

**Freshness over completeness:** for position data, a slightly stale-but-smooth estimate
beats a late-but-exact one. Drop stale packets; never block on retransmission (#04).

## 9.2 Accuracy & fidelity

| Aspect | Target | Notes |
|--------|--------|-------|
| Injected car position (with GPS) | within ~a car-length of true track position | needs ≥10 Hz, ≤2 m GPS (#04); RTK if available |
| Injected car position (timing-only) | order-correct; on the correct track section | interpolated; lower fidelity is acceptable & flagged |
| Injected car motion | smooth, no teleport/strobe | hard requirement (#04 §4.3, #05) |
| Official lap/order (real class) | exact = official | never overridden (#08) |
| Timed-finish trigger | exact real-leader completion from official timing | not RaceSync-estimated (#06 §6.4) |

Every position carries a **quality/source flag** surfaced to drivers/operator, so low
fidelity is *visible*, not silently misleading.

## 9.3 Reliability, availability & degraded modes

The event runs once, live; graceful degradation matters more than perfection.

| Failure | Behaviour | Surfaced as |
|---------|-----------|-------------|
| GPS feed loss | fall back to timing interpolation; phantoms dead-reckon then degrade (#04) | health alarm, per-car quality flag |
| Timing feed loss | hold last order; widen uncertainty; alarm | health alarm |
| Both position sources lost | injection suspended cleanly (no wild phantoms); **state sync + audio continue** | major alarm; operator decision |
| Injection/sim failure | **fall back to Strategy 3** (state-sync + overlay) without losing state/audio/scoring (#05) | major alarm |
| Audio ingress (`MRA-RMC`) loss | machine state cues continue; voice relay alarmed (#07) | alarm |
| Edge↔cloud link loss | **edge Race State Engine stays authoritative**; cloud holds last-known; no blind state changes (#03 §3.4) | major alarm |
| Operator console down | last state persists; restart restores from event log | — |

**Design rules:**
- **No single failure may corrupt the race state or scoring** — only reduce fidelity.
- **Injection is the first thing sacrificed**, never the state/audio/scoring backbone.
- **Manual override always available** — operator can freeze the virtual field, suspend
  injection, drop a phantom, or set state by hand.
- **No automatic green/Code 60 changes when blind** — if inputs are untrustworthy, the
  system holds and alarms rather than guessing.

**Targets:** no unrecoverable crash during a race; recovery from any single component
restart in **≤ 30 s** using the persisted event log; the audit log is **append-only and
durable** across restarts.

## 9.4 Scalability

| Dimension | v1 target | Headroom path |
|-----------|-----------|---------------|
| Real cars (phantoms) | up to **56** (field max, #02) | injection scaling validated in #05 spikes (esp. Strategy 2 per-client cost) |
| Virtual drivers | **≤24** remote | within mainstream online session limits; splits/multi-session deferred |
| Position update rate | ≥10 Hz/car ingestion; injection rate per platform | bus designed for UDP-style high-rate streams (#03) |
| Event duration | full race (≈ a few hours incl. SC) | continuous operation; logs rotate without loss |

## 9.5 Sync-health observability

The Health Monitor (C7) is a first-class feature, not an afterthought. It continuously
reports, to the operator:

- Per-source feed **freshness/rate/drop-rate** (#04).
- **Injection lag** (real→virtual) and phantom count/health (#05).
- **Audio delay** and ingress status (#07).
- **State divergence** checks (is any field racing under the wrong state?).
- **Clock alignment** drift.
- A single **GO / DEGRADED / FAULT** summary with drill-down, plus alarms with clear,
  actionable text.

Health and all key events feed the **audit log** for live diagnosis and post-event review.

## 9.6 Connectivity

- Trackside connectivity at SMSP is **shared and variable** (#01 A3). The system MUST
  tolerate jitter, packet loss, and brief outages without state corruption.
- Position transport favours **UDP-style with sequence numbers** (freshness > guaranteed
  order); control/state uses reliable transport with idempotent, replayable messages.
- Edge buffering covers short outages; on reconnect, backfill where supported else resync +
  log the gap (#04 §4.3).
- Remote virtual drivers connect to the cloud sim host; their individual connection quality
  is their own (standard online-sim assumption), but the **server↔RaceSync** path is
  monitored.

## 9.7 Security & access control

- **Operator console** access is restricted (only authorised RaceSync operators can trigger
  Code 60 / fire the chequer / override).
- **Audio bridge** is **listen-only** on `MRA-RMC` and **provably cannot transmit** (#07) —
  protecting the integrity of the official one-way channel (Art. 10.7).
- **Feed credentials** (X2, Zello, sim server) are secrets, stored securely, never in the
  repo or logs.
- **Audit log** is tamper-evident/append-only for results integrity and dispute resolution.
- No PII beyond what the event already holds (driver identities); handle per the event's
  privacy obligations.

## 9.8 Compliance & sanctioning (MA)

- RaceSync MUST NOT cause a breach of the Special Regulations or CRSR for the **real** race
  (#01 A1); it mirrors official decisions and never alters real timing, flags, penalties, or
  pit rules.
- The **new procedures** RaceSync introduces — virtual Code 60, the timed virtual finish,
  relaying `MRA-RMC` to virtual participants — MUST be expressible as event regulations,
  briefable to drivers, and **approved by MA / the Organiser** (TBC-5, TBC-6; O-12, #10).
- The virtual class running under an MA permit is an **organiser/MA matter**; RaceSync
  provides the auditable timing/scoring to support it.

## 9.9 Operability

- **One operator, one screen** for live running (#01 A4): clear state, big obvious controls,
  guarded destructive actions, unambiguous health.
- **Pre-race checklist & dry-run mode** (replay recorded feeds, #04) to validate the full
  chain before the green flag.
- **Briefing artifacts**: the timed-finish and Code 60 rules must be clearly communicable to
  virtual drivers pre-event.

## 9.10 Testability

- All external inputs (timing, GPS, audio, sim telemetry) are recordable and **replayable**
  (`ReplaySource`, #04), so the whole system can be exercised off recorded events without a
  live track.
- Components are bus-decoupled (#03) and individually testable against recorded streams.
- The #05 spike doubles as the first integration test of ingestion → injection → telemetry.
