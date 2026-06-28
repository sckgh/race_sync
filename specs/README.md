# RaceSync — Specifications

RaceSync is a system for running a **hybrid motor race**: a field of real race cars on
a physical circuit and a smaller field of remote sim racers, racing *the same race at
the same time*, scored as separate classes, governed under the same Motorsport
Australia (MA) permit.

The flagship target event is the **Viola Private Wealth Sydney 300** — a 300 km / 77-lap
endurance race at **Sydney Motorsport Park (SMSP)** under MA Circuit Race regulations
(see [`02-event-context.md`](02-event-context.md)).

## What RaceSync does

1. **Injects real cars into the virtual world.** Live position data from each real car
   (via MyLaps timing and/or GPS) is streamed into the simulator so virtual drivers
   race against moving representations of the real field.
2. **Synchronises race state both ways at the control level.** The real race's flag
   state drives the virtual race: a real **Safety Car** becomes a virtual **Code 60**;
   the virtual race takes the chequered flag the instant the real leader completes
   300 km (a *timed* finish).
3. **Bridges race-management audio.** The event's existing one-way Zello race-management
   channel (`MRA-RMC`) is relayed into virtual drivers' headsets, so a single Race
   Control voice reaches real and virtual participants alike.
4. **Scores the two fields together.** Real and virtual cars are timed and classified as
   separate classes within one combined result.

## How to read these specs

Read in order for the full picture; each file is self-contained.

| # | Document | What it covers |
|---|----------|----------------|
| — | [`00-glossary.md`](00-glossary.md) | Terms, acronyms, units |
| 01 | [`01-vision-and-scope.md`](01-vision-and-scope.md) | Goals, non-goals, personas, success criteria |
| 02 | [`02-event-context.md`](02-event-context.md) | SMSP + Sydney 300 facts the system must honour |
| 03 | [`03-system-architecture.md`](03-system-architecture.md) | Components, data flow, deployment topology |
| 04 | [`04-data-feeds.md`](04-data-feeds.md) | MyLaps X2 timing vs. true GPS; ingestion & the position model |
| 05 | [`05-sim-injection-feasibility.md`](05-sim-injection-feasibility.md) | **The crux:** can we put real cars in a sim? Platform comparison + recommendation |
| 06 | [`06-race-state-sync.md`](06-race-state-sync.md) | Flags, Safety Car→Code 60, rolling start, timed finish |
| 07 | [`07-audio-race-management.md`](07-audio-race-management.md) | Zello `MRA-RMC` one-way bridge to virtual drivers |
| 08 | [`08-scoring-and-classification.md`](08-scoring-and-classification.md) | Virtual class, combined timing, results |
| 09 | [`09-non-functional-requirements.md`](09-non-functional-requirements.md) | Latency, reliability, connectivity, security, compliance |
| 10 | [`10-delivery-plan-and-risks.md`](10-delivery-plan-and-risks.md) | Phased roadmap, de-risking spikes, open questions |

## Status

These are **draft specifications only** — no implementation. They capture the agreed
direction from the initial scoping conversation and surface the decisions and unknowns
that must be resolved before build.

### Key decisions captured so far

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Sim integration model | **Live car injection** (real cars rendered as moving cars in the sim) | Most immersive for virtual drivers; highest technical risk — see #05 |
| Sim platform | **Most feasible wins** — ranked in #05, not pre-committed to iRacing | iRacing's SDK cannot spawn externally-driven cars; moddable sims can |
| GPS / position source | **Pluggable** — support both MyLaps X2 timing and true GPS lat/long | Real source TBD; design must not hard-depend on either |
| Race audio | **Bridge existing Zello `MRA-RMC`** (one-way) | Single source of truth; reuses sanctioned event infrastructure |
| Safety Car → Code 60 | **Manual** trigger by a Race Control operator | Reliable, human-in-the-loop; automation deferred |
| Virtual field size | **≤24 remote drivers**, own scoring class | Fits mainstream online session limits |

### Biggest open question

**Can real cars be injected into the chosen simulator as moving cars at acceptable
fidelity and latency?** This is unresolved and gates the whole concept. #05 defines the
feasibility spike that must run before any further commitment.
