# 05 — Sim Injection Feasibility (the crux)

> **This is the make-or-break document.** The agreed product model is **live car
> injection**: real cars appear as *moving cars inside the simulator* so virtual drivers
> race against them. Whether that is achievable — and on which platform — is the single
> biggest risk in the project. The platform is **not pre-committed**; "whatever is most
> feasible" wins. This document states the problem honestly, compares candidates, gives a
> recommendation, and defines the spike that must settle it **before** further build.

## 5.1 The hard problem, stated plainly

We need to place **N phantom cars** (one per real car, up to 56) into a running sim
session, **update their world position ~10–60×/second** from externally-supplied data, and
have **≤24 human virtual drivers** see them as normal opponents — able to judge closing
speed, draft, and avoid them — all at **low, stable latency**.

The difficulty is that **mainstream racing sims are built to be authoritative about car
state.** A car's position is the *output* of the physics engine driven by a local human or
the sim's own AI. There is generally **no supported API to say "car #12 is now at (x,y),
facing θ, doing 180 km/h"** from outside. That one missing capability — *external
authorship of car world-state* — is what the entire concept hinges on.

Two broad strategies exist, and every candidate platform is really a bet on one of them:

- **Strategy 1 — Authoritative override:** a server/plugin layer that *sets* each phantom
  car's state every tick. Cleanest result if the platform allows it; most platforms don't.
- **Strategy 2 — Puppet driving:** run a real (or headless) sim *client* per phantom and
  *drive* it via synthetic inputs / an autopilot that chases the target position. Always
  "possible" but fights the physics engine, scales poorly, and risks unstable motion.

A third, **fallback strategy**, abandons in-world injection:

- **Strategy 3 — Parallel race + shared visualization (state-sync fallback):** virtual
  drivers race their *own* clean session; real cars are **not** in their world, but a
  combined **track-map/AR overlay** shows both fields, and race *state* (Code 60, timed
  finish, leaderboard) is fully synced. Lower immersion, **dramatically lower risk**, and
  delivers most of the event value. This is the safety net if Strategies 1/2 fail to hit
  fidelity/latency targets.

## 5.2 Candidate platform comparison

Assessed against: external car-state authorship, SDK openness, SMSP availability, online
session model for ≤24 remote drivers, and overall injection feasibility.

| Platform | External car-state authorship | SDK / mod openness | SMSP track | Inject feasibility | Notes |
|----------|------------------------------|--------------------|-----------|--------------------|-------|
| **iRacing** | **No.** SDK is **read-only** telemetry + a limited *broadcast* control API (cameras, replay, chat, pit commands). Cannot spawn or position externally-driven cars. | Closed, ToS-restricted; memory hooks would breach ToS & anti-cheat. | **Official, laser-scanned** (multiple configs) | **Very low** for true injection | Best track & netcode, worst for our core need. Realistic role: Strategy 3 only. |
| **Assetto Corsa (original)** | **Partially.** Huge modding surface: shared memory, Python/Lua apps, Custom Shaders Patch, and an **AC server UDP plugin**. No clean "teleport any car" call, but the openness makes Strategy 1/2 experiments viable (custom server, AI-path scripting, client puppets). | **Very open** (community SDKs, source-adjacent tooling) | High-quality **mods** exist (community, verify config) | **Medium–High** (highest of the mainstream sims) | Most promising mainstream candidate for real injection. |
| **rFactor 2 / Le Mans Ultimate** | **Partially.** Mature **InternalsPlugin** SDK with control hooks; stronger "official plugin" story than AC. Still no documented arbitrary car-teleport. | **Open** internals SDK | **Mods** exist (verify) | **Medium** | Strong plugin model; smaller modding community than AC. |
| **Assetto Corsa Competizione** | **No.** Shared-memory + broadcasting API are **read-only**. | Closed (UE4, no car authorship) | GT-only content; no SMSP | **Very low** | Rule out for injection. |
| **BeamNG / custom engine / game-engine twin** | **Yes** (you own the world) | N/A — you build it | Build from survey/GPS | **High** *capability*, **High** *build cost* | A bespoke "digital twin" renderer can place cars trivially, but you forfeit a turn-key racing sim for the virtual drivers. Possible for the *visualization* half of Strategy 3. |

### Reading of the table

- **iRacing's strength (track + netcode) is irrelevant to our core requirement**, and its
  closed/anti-cheat posture makes Strategy 1/2 both technically blocked and ToS-violating.
  iRacing is therefore a candidate **only for Strategy 3** (own race + external overlay).
- **Assetto Corsa (original) is the most feasible mainstream platform for true injection**,
  because its openness is the only thing that makes *external car-state authorship* even
  approachable. **rFactor 2/LMU** is the credible alternative on the strength of its
  internals plugin SDK.
- A **bespoke engine twin** maximises injection capability but trades away the off-the-shelf
  driving experience — best reserved for the *visualization* layer, not the racing layer.

## 5.3 Recommendation

A **fidelity-laddered, two-track** approach — commit to neither a platform nor a strategy
until the spike produces evidence:

1. **Primary injection bet: Assetto Corsa (original)**, attempting **Strategy 1** (custom
   server/plugin authoring phantom-car state) and, if that stalls, **Strategy 2** (puppet
   clients with a position-chasing autopilot). Rationale: only AC's openness gives external
   car-state authorship a realistic chance on a turn-key sim, it has SMSP-capable mods, and
   it comfortably hosts ≤24 online drivers.
2. **Secondary injection bet: rFactor 2 / LMU** via the InternalsPlugin, evaluated in
   parallel if resourcing allows, as a hedge on AC.
3. **Mandatory fallback: Strategy 3 (state-sync + combined visualization)**, which can run
   on **any** platform including iRacing. This is the **guaranteed-deliverable** baseline:
   even if no sim accepts injected cars at acceptable fidelity, the event still gets synced
   flags, Code 60, timed finish, audio bridge, and a combined leaderboard with a shared
   track-map overlay. **Build the architecture so Strategy 3 is always available**, with
   injection layered on top where the spike proves it out.

This honours "live car injection" as the **target** while guaranteeing the event is not
hostage to an unproven capability.

## 5.4 The feasibility spike (run before any further commitment)

**Goal:** answer, with evidence, *"Can we inject moving cars into a sim at acceptable
fidelity and latency?"* and *"On which platform/strategy?"*

### Spike S1 — AC Strategy 1 (authoritative override)
- Stand up an AC dedicated server + UDP plugin / custom plugin.
- Author **2–4 phantom entries** and attempt to set their position every tick from a
  **recorded GPS/position trace** (from #04).
- A human joins online and observes: are the phantoms visible, smoothly moving, collidable/
  avoidable, correctly placed on track?
- **Measure:** injection apply rate, end-to-end position latency (trace → on-screen), motion
  smoothness, max phantom count before degradation, netcode behaviour for the human client.

### Spike S2 — AC Strategy 2 (puppet clients) *(only if S1 blocks)*
- Run one headless/again client per phantom; drive via an autopilot chasing the target `s`/
  speed from the trace. Measure the same metrics + per-client resource cost (→ scaling to
  56).

### Spike S3 — rFactor 2 / LMU InternalsPlugin *(parallel hedge)*
- Equivalent of S1 using the rF2 internals/control plugin.

### Spike S4 — Strategy 3 baseline (must succeed)
- On iRacing **or** AC: virtual drivers race a clean session; build a **combined track-map
  overlay** placing real cars from the position model, with synced flags/Code 60/leaderboard.
- Confirms the guaranteed-deliverable path and exercises #04/#06/#08 end to end.

### Pass/fail targets (refine in #09)
| Metric | Target for "injection viable" | Hard fail |
|--------|-------------------------------|-----------|
| End-to-end position latency (real → virtual screen) | ≤ ~250 ms typical | > ~500 ms sustained |
| Phantom motion | smooth, no teleport/strobe | visible jumps that break racing |
| Phantom count at fidelity | ≥ enough for the real field (scale path to 56) | can't exceed a handful |
| Collidability/avoidance | drivers can judge & avoid | phantoms non-interactive/ghost-only with no value |
| Virtual client stability | stable online session for ≤24 | crashes/desyncs under load |

**Decision gate:** if **no** injection spike (S1–S3) clears the targets, the project ships
on **Strategy 3** and live injection becomes an R&D track, not a v1 commitment. The
operator/scoring/audio/state work (#06–#08) is unaffected either way.

## 5.5 Cross-cutting constraints on whatever wins

- **ToS / anti-cheat:** the chosen mechanism MUST be within the platform's terms. Memory
  injection into a protected client (notably iRacing) is excluded. Prefer official plugin/
  server SDKs (AC server plugin, rF2 internals).
- **Determinism for Code 60:** the platform must let us **impose virtual Code 60** on the
  *human* virtual field (speed cap / penalty enforcement) — see #06. Verify per platform in
  the spike.
- **Track fidelity vs config:** the SMSP config (TBC-1) must exist or be buildable on the
  chosen platform with geometry matching the position-model track frame (#04).
- **Headless/server cost:** Strategy 2's per-car client cost gates scaling to 56 — measure
  early.
- **Interface isolation:** per #03, C3 (injection) and C4 (telemetry) sit behind interfaces
  so the platform decision can change without disturbing ingestion, state, audio, scoring.

## 5.6 Requirements

- **F-05-1** The injection adapter MUST be implemented behind a platform-agnostic interface
  (`SimInjectionAdapter`) with at least one concrete implementation chosen by spike outcome.
- **F-05-2** The system MUST support the **Strategy 3 fallback** on any platform, regardless
  of whether injection is enabled.
- **F-05-3** The chosen injection mechanism MUST comply with the platform's ToS and anti-
  cheat rules (no prohibited memory injection).
- **F-05-4** Injected phantom motion MUST be smooth and non-teleporting (consumes #04's
  dead-reckoning/quality model).
- **F-05-5** The platform MUST allow imposing **virtual Code 60** on the human virtual field
  (#06); if it cannot, that platform is disqualified for injection.
- **NF-05-1** Injection end-to-end latency targets per #09; measured continuously by C7.
