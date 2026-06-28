# 06 — Race State Synchronisation

The Race State Engine (C2, #03) is the single source of truth for the state shared between
the real and virtual fields. This document defines that state machine and the four
transitions that matter most: **going green (rolling start)**, **Safety Car → Code 60**,
**back to green**, and the **timed finish**.

## 6.1 Shared race state machine

```
        ┌──────────┐   operator: arm   ┌───────────┐  green (real start)  ┌──────────┐
        │ PRE-RACE │ ────────────────▶ │ FORMATION │ ───────────────────▶ │  GREEN   │
        └──────────┘                   └───────────┘                       └────┬─────┘
                                                                                │  ▲
                                                          SC deployed (operator) │  │ SC withdrawn
                                                                                ▼  │ (operator) + restart
                                                                          ┌───────────────┐
                                                                          │ NEUTRALISED   │
                                                                          │ (real: SC /   │
                                                                          │  virtual:     │
                                                                          │  CODE 60)     │
                                                                          └───────┬───────┘
                                                                                  │
                                  real leader completes 300 km / 77 laps          │ (can occur from
                                  ──────────────────────────────────────────────▶│  GREEN or NEUTRALISED)
                                                                                  ▼
                                                                            ┌───────────┐
                                                                            │ CHEQUERED │ (timed finish,
                                                                            └───────────┘  virtual field)
```

- The engine holds **one global state** plus per-field projections (what each field is told).
- **Laps always count** in both fields, including under neutralisation (Art. 11.1.2).
  Neutralisation slows the field; it does not pause the race or the finish trigger.
- Every transition is an event on the bus (#03) consumed by Injection (C3), Audio (C5),
  Scoring (C6), and the Console (C8), and is written to the audit log with source
  (operator vs detected) and timestamp.

## 6.2 Going green — the rolling start

The real race uses a **rolling start** (Art. 8, CRSR 5.5): formation behind the official
vehicle at 75–85 km/h, then **start = red lights extinguished** (Art. 8.11). RaceSync must
release the **virtual field in sync** so both go racing together.

- **Trigger:** primarily an **operator "GREEN" action** on the console at the moment the
  real start is given (the operator is watching/【hearing it on `MRA-RMC`). Optionally
  assisted by a detected timing transition (first flying lap / leader pace), but the
  operator action is authoritative in v1 (consistent with the manual-trigger decision).
- **Virtual start procedure:** the virtual field runs its **own equivalent rolling start**
  (formation lap in the sim) and is **held** until the engine emits `green`. On `green`,
  the virtual field is released. The exact sim mechanism (pace car / hold-and-release) is a
  platform detail validated in the #05 spike.
- **Alignment goal:** both fields begin green-flag racing within a small window so the
  *timed finish* is fair. The acceptable start-skew is a tunable (target in #09); any known
  skew is recorded so Scoring can account for it.

> **Why this matters for fairness:** because the virtual finish is *timed* off the real
> leader (6.4), any difference in when the two fields go green is effectively a handicap.
> The start-skew is measured and logged, and surfaced to officials.

## 6.3 Safety Car → Code 60

The core neutralisation mapping. A real **Safety Car** period becomes a virtual **Code 60**
(full-course 60 km/h limit, no overtaking) for the virtual field.

### Trigger (manual, per decision)
- The **operator** sets `NEUTRALISED` on the console when the real Safety Car is deployed
  (they learn of it via Race Control / `MRA-RMC`, where SC deployment is announced —
  Art. 10.2), and clears it when the SC is withdrawn and the restart is given.
- **Two clicks, guarded:** deploy and withdraw are deliberate, confirmable actions with
  clear current-state display, to avoid accidental field-wide neutralisation. (Automation
  and detection assistance are deferred — O-2, #10.)

### Effect on the virtual field (Code 60)
- All virtual cars must drop to **≤60 km/h**; **no overtaking**; hold position.
- Enforcement depends on platform capability (validated in #05): ideally a sim-enforced
  speed cap; otherwise **RaceSync-enforced** via Scoring penalties for speeding/positions
  gained under Code 60 (C6), with audio + on-screen warning.
- **Laps continue to count** under Code 60 (mirrors Art. 11.1.2). Code 60 neutralises pace,
  not scoring.

### Effect on injected real cars
- Under real Safety Car the real field bunches and slows; the **phantom cars naturally
  reflect this** because their motion comes from live position data (#04) — no special
  handling needed beyond the normal feed. The virtual Code 60 keeps the *human* virtual
  field congruent with that slowed real field.

### Effect on audio
- The same `MRA-RMC` audio that announces the real SC is already relayed to virtual drivers
  (#07); RaceSync adds a clear visual/audio **"CODE 60"** state indicator for the virtual
  field on top.

### Restart
- On `NEUTRALISED → GREEN`, the virtual field returns to racing under a defined restart
  procedure (e.g. green announced on audio + on-screen). Restart skew is logged like the
  start skew.

### Edge cases
| Case | Handling |
|------|----------|
| SC during CPS window | Real CPS rules unchanged (Art. 15.5/15.6 — window not extended, pit may stay open). RaceSync does not alter real pit rules; virtual pit rules per O-7 (#10). |
| Multiple SC periods | State machine cycles GREEN↔NEUTRALISED any number of times; each logged. |
| SC very near the finish | If the real leader completes the distance under SC, the **timed finish still fires** (6.4); virtual field is chequered from Code 60. |
| Operator misclick | Guarded confirm + instant revert; all transitions in audit log. |

## 6.4 The timed finish

The virtual race is **timed**: virtual cars receive the chequer the instant the **real
leader** completes the full race distance — **not** after a fixed virtual lap count.

- **Trigger source:** the **real leader's race completion** — i.e. the leader crossing the
  line to complete **lap 77 / 300 km**, taken from **authoritative MyLaps timing**
  (`timing.event: race_completed`), not RaceSync's own estimate (#01 A2). The leader's lap
  count is already a tracked signal (also used for the CPS window, #02).
- **Operator confirmation:** v1 keeps a human in the loop — the engine **arms** the chequer
  when timing reports the leader's final lap and the **operator confirms** firing it (one
  guarded action), so a timing glitch can't end the virtual race spuriously. (A fully
  automatic mode is a later option — O-5, #10.)
- **Effect:** engine → `CHEQUERED`. The virtual field takes the chequer **at their current
  position on track**; each virtual car is classified on **laps completed + position when
  the chequer fell** (endurance "timed race" convention), in their own class (#08).
- **No virtual lap target:** virtual cars are **not** required to complete 77 laps; they
  complete **as many as they can before the real leader finishes**. This is the essence of
  the timed format and must be briefed to virtual drivers.
- **Fairness inputs:** start-skew (6.2) and any neutralisation-skew (6.3) are recorded so
  officials can judge/adjust the virtual classification if required.

## 6.5 What RaceSync does NOT control

- It does **not** decide the real race result, real penalties, or real flags — those are
  official (#02 §2.7). RaceSync **mirrors** them.
- It does **not** extend or alter the real CPS window or real pit rules.
- It does **not** transmit on `MRA-RMC` (one-way; Art. 10.7) — it relays only (#07).

## 6.6 Requirements

- **F-06-1** The engine MUST maintain one shared race state (PRE-RACE, FORMATION, GREEN,
  NEUTRALISED, CHEQUERED) and emit every transition on the bus with source + timestamp.
- **F-06-2** Going green MUST be operator-triggered, releasing the virtual field in sync
  with the real rolling start; start-skew MUST be measured and logged.
- **F-06-3** The operator MUST be able to set/clear NEUTRALISED (Safety Car → Code 60) via
  guarded, confirmable actions, with current state always visible.
- **F-06-4** Under Code 60 the virtual field MUST be limited to ≤60 km/h with no overtaking,
  enforced by the sim where possible and by Scoring penalties otherwise; **laps MUST keep
  counting**.
- **F-06-5** The timed finish MUST trigger from authoritative real-leader race completion
  (MyLaps), with operator confirmation in v1, classifying virtual cars on laps+position at
  chequer.
- **F-06-6** All state transitions MUST be reversible/auditable and MUST NOT alter official
  real-race timing, flags, penalties, or pit rules.
- **F-06-7** The engine MUST tolerate multiple SC/Code 60 cycles and SC-at-finish without
  losing finish correctness.
- **NF-06-1** State-transition propagation latency targets per #09 (no field racing green
  while the other is neutralised beyond the target window).
