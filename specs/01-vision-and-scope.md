# 01 — Vision & Scope

## 1.1 Vision

Run one race across two worlds. A field of real cars laps Sydney Motorsport Park while a
field of remote sim racers laps a virtual SMSP **at the same time, under the same race
control**. The two fields see and respond to each other: virtual drivers race against
moving representations of the real cars, both fields obey the same flags, and a single
Race Control voice reaches everyone. At the end, one combined result lists both classes.

RaceSync is the connective tissue that makes that possible: it ingests live position and
timing from the real cars, injects them into the simulator, maps real race-control state
onto virtual race-control state, bridges the race-management audio, and produces unified
timing and scoring.

## 1.2 The reference scenario

From the initial brief and the 2026 Viola Private Wealth Sydney 300 Special Regulations:

- Real cars run a **300 km / 77-lap** race at SMSP under an MA permit.
- A **virtual field (≤24 remote drivers)** runs the same race in a simulator, as its **own
  scoring class**, also intended to be under an MA permit.
- The virtual race is **timed**: virtual cars receive the chequered flag at the moment the
  **real leader** completes the full race distance — not after a fixed virtual lap count.
- A real-world **Safety Car** deployment triggers **Code 60** for the virtual field.
- A **one-way race-management audio channel** (the event's Zello `MRA-RMC`) reaches both
  real and virtual participants.

## 1.3 Goals (what success looks like)

| # | Goal | Measured by |
|---|------|-------------|
| G1 | Real cars appear as moving cars in the virtual world | Virtual drivers can see/avoid/race real-car representations with usable fidelity (target accuracy & latency in #09) |
| G2 | Race state stays consistent across both fields | Flag/SC/Code 60 transitions propagate within target latency (#06, #09); no field races green while the other is yellow |
| G3 | One race-management voice reaches everyone | `MRA-RMC` audio is audible to virtual drivers with acceptable delay (#07) |
| G4 | Both fields finish together, fairly | Virtual chequer fires on real-leader race completion; results show both classes correctly (#06, #08) |
| G5 | The system is operable by a small crew at a live event | One operator console; clear failure modes and manual overrides (#03, #09) |

## 1.4 Non-goals (explicitly out of scope, at least for v1)

- **Replacing official timing or race control.** RaceSync consumes official timing and
  mirrors official decisions; it is not the system of record for the real race result.
- **Two-way audio.** The race-management channel is one-way (Race Control → participants),
  matching the event regs. Driver-to-control and team radio are out of scope.
- **Physics-accurate car behaviour for injected cars.** Injected real cars need to be in
  the right place at the right time and behave plausibly; they need not model the real
  car's exact dynamics.
- **Automated Safety Car detection.** v1 uses a manual operator trigger (#06). Automation
  is a later enhancement.
- **Real cars seeing virtual cars in the physical world.** No AR/HUD in real cars. The
  cross-field awareness is virtual-only (virtual drivers see real cars; real drivers do
  not see virtual cars beyond what Race Control relays).
- **Betting, wagering, or money-handling features.**
- **Multi-event/season management, championship points.** Single-event focus first.

> Note on "real drivers see virtual cars": the brief asks that audio reach *both* virtual
> and actual participants — that is in scope (#07). Visually injecting virtual cars into
> real drivers' field of view is not.

## 1.5 Personas

| Persona | Needs from RaceSync |
|---------|---------------------|
| **Race Control operator (RaceSync console)** | Trigger Code 60, monitor sync health, fire the virtual chequer, override on failure. Sits beside official Race Control. |
| **Virtual driver (remote sim racer)** | A faithful, low-latency view of the real field; correct flags/Code 60; race-control audio; fair scoring in their class. |
| **Real driver / team** | Unaffected normal race experience; existing Race Receiver / Zello unchanged. |
| **Timing & scoring official** | Combined, correct results with classes clearly separated; an audit trail. |
| **Spectator / broadcast** | (Stretch) a combined view of both fields. Not a v1 commitment but the data model should not preclude it. |

## 1.6 Constraints & assumptions

- **A1 — Sanctioning.** Both fields run under MA permits; RaceSync must not cause the
  event to breach the Special Regulations or CRSR. Where RaceSync introduces new
  procedures (Code 60, timed virtual finish), these must be expressible as event
  regulations and briefable to drivers.
- **A2 — Real timing is authoritative.** Lap counts, the leader, and race completion for
  the *real* race come from official MyLaps timing, not from RaceSync's own estimates.
- **A3 — Trackside connectivity is constrained.** Cellular/Wi-Fi at SMSP is shared and
  variable; the architecture must tolerate jitter and brief outages (#09).
- **A4 — Small operating crew.** Assume one RaceSync operator plus normal event officials.
- **A5 — Position data source is not yet fixed.** The system must support both MyLaps X2
  timing and true GPS lat/long, and degrade gracefully if only the coarser source is
  available (#04).
- **A6 — Sim platform is not pre-committed.** Choice follows feasibility (#05).
- **A7 — Track configuration is assumed Gardner GP** (≈3.896 km × 77 = 300 km) **pending
  confirmation** from the Supplementary Regulations.

## 1.7 Out-of-the-box questions deferred to #10

Field size scaling beyond 24, multi-class virtual grids, broadcast overlay, and automated
SC detection are all tracked as open items in [`10-delivery-plan-and-risks.md`](10-delivery-plan-and-risks.md).
