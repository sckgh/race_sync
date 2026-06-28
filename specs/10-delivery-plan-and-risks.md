# 10 — Delivery Plan, Risks & Open Questions

A phased path that **de-risks the unknowns first**, keeps a guaranteed-deliverable baseline,
and only invests in the hardest capability (live injection) once it's proven.

## 10.1 Guiding strategy

1. **Prove the crux before building around it.** Live car injection (#05) is the biggest
   risk; run the spike before committing the platform or the rest of the build.
2. **Always have a shippable baseline.** Strategy 3 (state-sync + combined visualization,
   #05) delivers most event value with low risk and is platform-agnostic. Build it first;
   layer injection on top where the spike proves it.
3. **Decouple via the bus and interfaces** (#03/#04/#05) so the platform/source decisions can
   change late without rework.
4. **Replay everything** (#09 §9.10) so we can build and test off recorded feeds without a
   live track.

## 10.2 Phases

### Phase 0 — Discovery & access (resolve the TBCs)
**Goal:** turn unknowns into facts. No code dependency on guesses.
- Confirm SMSP **circuit config** (TBC-1) and obtain track survey/geometry for the position
  frame (#04).
- Confirm **MyLaps X2 live feed** access + protocol (TBC-2); capture a sample feed.
- Confirm **GPS hardware** presence/rate/accuracy/transport (TBC-3); capture a sample trace.
- Confirm **`MRA-RMC` relay** access/credentials (TBC-6).
- Open the **MA / Organiser conversation** on virtual class, Code 60, timed finish, and
  audio relay (TBC-5, O-12).
- **Exit:** sources characterised; sample recordings in hand; sanctioning path understood.

### Phase 1 — Feasibility spike (#05) ← **highest priority**
**Goal:** answer "can we inject moving cars, and on what platform?" with evidence.
- Run spikes **S1 (AC override)**, **S2 (AC puppet, if needed)**, **S3 (rF2/LMU)**, and
  **S4 (Strategy 3 baseline)** against recorded GPS + timing traces.
- Measure against the #05 / #09 latency & fidelity targets.
- **Decision gate:** pick **injection platform+strategy** *or* fall back to Strategy 3 for
  v1 and move injection to an R&D track.
- **Exit:** documented go/no-go on injection; chosen platform; measured latency budget.

### Phase 2 — Backbone (works regardless of spike outcome)
**Goal:** the parts that ship no matter what.
- **Feed Ingestion + Position Model + fusion** (#04) with `MyLapsX2Source`, `GpsUdpSource`,
  `ReplaySource`.
- **Race State Engine** (#06): state machine, operator-triggered GREEN / Code 60 / timed
  finish (with confirm), audit log.
- **Operator Console + Health Monitor** (#03/#09).
- **Audio Bridge** (#07): listen-only `MRA-RMC` relay + machine state cues.
- **Sim Telemetry Reader + Scoring** (#08) for the virtual class; real-class mirror.
- **Strategy 3 combined visualization** (track-map overlay) — the guaranteed deliverable.
- **Exit:** a full hybrid race runnable end-to-end **without** in-world injection (virtual
  field races clean; real field shown on overlay; state/audio/scoring synced).

### Phase 3 — Injection (only if Phase 1 says go)
**Goal:** real cars as moving cars in-world.
- Implement the chosen `SimInjectionAdapter` (#05).
- Phantom lifecycle: spawn/scale toward field size, smooth motion from Position Model,
  degrade/park on data loss (#04), virtual Code 60 enforcement (#06).
- Integrate into the Phase 2 backbone behind the C3 interface.
- **Exit:** injection meets latency/fidelity targets in a dress rehearsal.

### Phase 4 — Trackside hardening & dress rehearsal
**Goal:** survive a live event.
- Degraded-mode drills (kill each feed/component; verify graceful behaviour, #09 §9.3).
- Dry-run from replay + a live practice/test session at SMSP if possible.
- Pre-race checklist, operator runbook, driver briefing materials (timed finish, Code 60).
- **Exit:** signed-off operations plan; MA/Organiser approvals in place.

### Phase 5 — Event & post-event
- Run the event; monitor health; operate overrides as needed.
- Capture full audit log; produce final classifications; post-event review feeds the next
  iteration (and the injection R&D track if deferred).

## 10.3 Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R1 | **No sim accepts injected moving cars at acceptable fidelity/latency** | Medium–High | High (kills "injection") | Phase-1 spike first; **Strategy 3 fallback** guarantees a shippable event regardless |
| R2 | **No MyLaps X2 live feed access** | Medium | High (kills primary data path) | Confirm early (TBC-2); fallback to GPS-derived timing or live-timing scrape (O-3); negotiate with timing provider |
| R3 | **GPS too coarse/slow or absent** | Medium | Medium (injection fidelity drops to interpolation) | Spec works timing-only (#04); pursue RTK GNSS if injection fidelity demands it |
| R4 | **MA won't permit a concurrent virtual class / Code 60 / audio relay** | Medium | High (sanctioning) | Engage MA/Organiser in Phase 0 (TBC-5, O-12); design procedures to be briefable & rule-expressible |
| R5 | **Trackside connectivity unreliable** | High | Medium | Edge-authoritative state (#03 §3.4); buffering; UDP freshness model; degrade-not-fail |
| R6 | **Injection puppet clients don't scale to field size** | Medium | Medium | Measure per-client cost in S2; prefer Strategy 1; cap phantom count & flag |
| R7 | **ToS/anti-cheat breach (esp. iRacing memory hooks)** | Low (if we follow #05) | High (bans/legal) | Only official plugin/server SDKs; iRacing limited to Strategy 3 |
| R8 | **Operator error triggers wrong state live** | Medium | Medium | Guarded confirms, instant revert, clear current-state display, audit log (#06) |
| R9 | **Fairness disputes over timed finish / start-skew** | Medium | Medium | Measure & log start/neutralisation skew; officials adjudicate; pre-agree method (O-12) |
| R10 | **Clock misalignment between sources** | Low | Medium | Single aligned clock + drift monitoring (#04, #09 §9.5) |

## 10.4 Open questions

Resolve before or during the phase noted.

| ID | Question | Resolve by |
|----|----------|-----------|
| O-1 | Final **sim platform + injection strategy** | Phase 1 (#05) |
| O-2 | Add **automated SC detection** assist to the manual trigger later? | Post-v1 (#06) |
| O-3 | Is **public live-timing scraping** an acceptable X2 fallback? | Phase 0 (#04) |
| O-4 | Exact **edge/cloud component split** | Phase 1–2 (#03) |
| O-5 | Fully **automatic timed-finish** firing (no operator confirm) later? | Post-v1 (#06) |
| O-6 | **Audio distribution method** to virtual drivers (sub-channel / in-sim / client) | Phase 1–2 (#07) |
| O-7 | **Virtual-class pit/stop rules** — mirror CPS, simplified, or none? | Phase 2 (#02/#08) |
| O-8 | **Virtual-class penalty schedule** (incl. Code 60 enforcement) | Phase 2 (#08) |
| O-9 | **Captioning/STT** of `MRA-RMC` for accessibility | Post-v1 (#07) |
| O-10 | Any **merged outright** (real+virtual) classification wanted? | Phase 2 (#08) |
| O-11 | **Virtual-class sub-divisions**? | Phase 2 (#08) |
| O-12 | **MA/Organiser sign-off** on timed-finish method, Code 60, audio relay | Phase 0–4 (#09) |
| O-13 | **Broadcast/spectator overlay** as a funded deliverable vs stretch | Post-v1 (#01/#08) |
| O-14 | Scaling **virtual field beyond 24** (splits, multi-session) | Post-v1 (#09) |

## 10.5 Definition of done (v1)

- A hybrid Sydney-300-style race runs end-to-end with: synced GREEN/Code 60/timed-finish,
  `MRA-RMC` audio + machine cues to virtual drivers, a combined two-class result, and a full
  audit log — **with injection if Phase 1 proved it, otherwise on the Strategy 3 baseline**.
- All degraded-mode drills (#09 §9.3) pass.
- MA/Organiser approvals for the virtual class and new procedures are in place.
