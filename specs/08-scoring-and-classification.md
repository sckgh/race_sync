# 08 — Scoring & Classification

RaceSync produces **one combined result** for the hybrid race, with **real and virtual cars
scored as separate classes**. It consumes authoritative real timing and live virtual
telemetry and reconciles them against the **timed finish** (#06).

## 8.1 Principles

1. **Real timing is authoritative for the real field.** Real lap counts, order, leader, and
   official penalties come from **MyLaps / official timing** (#01 A2, #02 §2.7). RaceSync
   *displays* them; it does not recompute them.
2. **Virtual timing comes from the sim.** Virtual lap/sector times, positions, and pit
   events come from the sim telemetry reader (C4, #03) — this is authoritative for the
   *virtual* class.
3. **Separate classes, one board.** Real and virtual cars are ranked **within their own
   class**; a combined view shows both. There is no merged outright order across the
   real/virtual divide unless officials explicitly want one (O-10, #10).
4. **The finish is timed.** Both classes are classified as of the **real leader's race
   completion** (#06 §6.4).
5. **Auditable.** Every classification input (timing events, state transitions, skews,
   penalties) is logged and replayable (#09).

## 8.2 Class model

| Class | Field | Timing source | Finish basis |
|-------|-------|---------------|--------------|
| **Real** (with Divisions A–E within it) | physical cars | MyLaps / official | Official 77-lap / 300 km result + official penalties |
| **Virtual** | sim cars (≤24) | sim telemetry (C4) | **Timed**: laps + on-track position at the moment the real leader completes 300 km |

- The real field keeps its **MA Divisions A–E** (#02 §2.2) *inside* the Real class — RaceSync
  surfaces them but does not assign them (officials do).
- The Virtual class is RaceSync's addition. Whether the virtual class itself is sub-divided
  (e.g. by car/skill) is **O-11** (#10); v1 assumes a single virtual class.

## 8.3 Virtual classification under the timed finish

At `CHEQUERED` (#06 §6.4):

1. Take each virtual car's **laps completed** and **track position (`s`)** at the chequer
   instant.
2. Rank by **laps completed desc, then track position `s` desc** (standard timed-race
   convention — furthest-along wins among equal laps).
3. Apply any **virtual-class penalties** (Code 60 speeding / positions gained under
   neutralisation, #06 §6.3; other virtual-class rules per O-8, #10).
4. Record **fairness adjustments inputs** — start-skew and neutralisation-skew (#06 §6.2/6.3)
   — alongside the result so officials can review or adjust. RaceSync flags them; officials
   decide.

> Virtual cars do **not** need 77 laps; they are classified on progress at the timed cutoff.
> This must be briefed to virtual drivers (it changes pit/stint strategy).

## 8.4 Combined timing view

A live view (operator + optional public/broadcast) showing both classes:

- Per car: number/ID, driver (resolved via MyLaps Driver ID / nomination, #04), class,
  division (real), laps, last/best lap, gap-in-class, pit status, and **data-quality
  indicator** (so a dead-reckoned or stale real car is visibly flagged — #04).
- Global banner: current **race state** (GREEN / CODE 60 / CHEQUERED), real leader lap
  (`/77`), CPS-window open/closed (informational, #02), and **sync health** summary (#09).
- The combined map/overlay (the Strategy-3 visualization, #05) can share this data layer —
  designing scoring and visualization off the same model keeps a broadcast view cheap to add
  later (a stretch goal, #01).

## 8.5 Reconciliation & integrity

- **Real result reconciliation:** because official penalties are **post-applied** by the
  Chief Timekeeper (#02 §2.7), RaceSync's real-class view is **provisional until official
  results are confirmed**, and must be able to **ingest/display the official final
  classification** as the source of truth. RaceSync's real-class numbers must never
  contradict official timing — where RaceSync interpolates (e.g. position between loops),
  that is clearly *position estimate*, not *timing*.
- **Virtual result integrity:** sim telemetry is captured continuously and the virtual
  result is reproducible from the recorded telemetry + state log.
- **Clock:** all results reference the aligned clock (#04 §4.2) so real and virtual events
  are comparable.

## 8.6 Outputs

| Output | Audience | Notes |
|--------|----------|-------|
| Live combined board | operator, (optional) public/broadcast | real-time, both classes |
| Provisional virtual classification | officials | at chequer, with skew/penalty annotations |
| Final virtual classification | officials | after virtual-penalty review |
| Real-class mirror | operator/broadcast | mirrors official; flagged provisional→final |
| Audit/export | officials, post-event | event log, per-class results, fairness annotations (format TBD) |

## 8.7 Requirements

- **F-08-1** Scoring MUST classify real and virtual cars as **separate classes** in one
  combined result.
- **F-08-2** Real-class data MUST derive from authoritative official/MyLaps timing and MUST
  be able to ingest/display the official final classification; RaceSync MUST NOT override it.
- **F-08-3** Virtual-class data MUST derive from sim telemetry (C4) and MUST be reproducible
  from recorded telemetry + state log.
- **F-08-4** Virtual classification MUST use the **timed finish**: laps + track position at
  the real-leader completion instant, with start/neutralisation skews recorded.
- **F-08-5** Scoring MUST apply virtual-class penalties (incl. Code 60 enforcement, #06) and
  annotate them in results.
- **F-08-6** The combined view MUST show race state, real-leader lap `/77`, per-car data-
  quality, and sync health.
- **F-08-7** All scoring inputs MUST be logged for audit and replay.

## 8.8 Open items (to #10)

- **O-7** Virtual-class pit/stop rules (mirror CPS? simplified? none?).
- **O-8** Virtual-class penalty schedule.
- **O-10** Whether any merged outright (real+virtual) order is wanted.
- **O-11** Virtual-class sub-divisions.
- **O-12** Official/MA sign-off on the timed-finish classification method.
