# 13 — Assetto Corsa Injection Spike Plan (run with AC open)

A concrete, grounded recipe for answering the project's central question on real hardware:
**can the real field appear as moving cars inside Assetto Corsa, well enough to race
against?** It refines the §5.4 spike for AC specifically, using what AC actually exposes
(researched, not assumed). Run it when you have AC in front of you.

## 13.1 What's already proven vs. what's open

- ✅ **Data path (Tier A):** the companion app ([`tools/ac_companion/`](../tools/ac_companion/))
  receives RaceSync phantom packets in AC and draws a 2D overlay. The wire format, decode,
  and `PhantomReceiver` are unit-tested. **This proves transport into AC works.**
- ❓ **Cars in the 3D world (Tier B):** showing the real field as 3D cars you can see and
  drive around — **the realistic target, not yet built.**
- ❓ **Collidable networked phantoms (Tier C):** real cars you can make contact with as if
  they were online opponents — **hard; likely out of reach with stock AC.**

## 13.2 Hard constraints (researched — design around these)

| Mechanism | What it can do | Can it author a car's world position? |
|-----------|----------------|----------------------------------------|
| **AC server UDP plugin (ACSP)** | Read car updates / lap times / collisions; admin: chat, kick, ballast, session, **start-penalty teleport only** | **No** — no arbitrary position-set command |
| **AI cars in multiplayer** | Only **spline-based traffic** via mods (AssettoServer), needs AI splines | **No** — true AI racers in MP is a known AC limitation |
| **Stock AC Python app API** | Read physics/graphics, draw UI | **No** — cannot move other cars |
| **CSP Lua + traffic system** | Spawn up to ~**2000 client-side car meshes**, move the `BODY` node freely each frame, optional colliders | **Yes (client-side, visual)** — the one viable path |

**Conclusion:** there is **no stock way to author *networked* car state**, so the realistic
injection is **CSP Lua client-side phantoms** (Tier B). Each virtual driver's client renders
the real field locally from the RaceSync feed. They are visual (and optionally locally
collidable), **do not appear in replays**, and are **not** networked race entries.

## 13.3 The injection ladder

| Tier | Mechanism | Outcome | Feasibility | Status |
|------|-----------|---------|-------------|--------|
| **A** | AC app overlay (done) | 2D map of the real field in-sim | High | ✅ built |
| **B** | **CSP Lua phantoms** | Real field as **3D visual cars** in the world, per client | **Medium–High** | **← spike this** |
| **C** | Puppet clients (one AC client per phantom, autopilot-driven) **or** modded `acServer` AI | **Collidable, networked** real-field cars | Low (heavy/at-risk) | defer/stretch |

### Reconciled architecture (how Tier B fits the event)

Tier B phantoms being **client-side** is not a problem — it composes cleanly with the
≤24-driver virtual field (specs/01):

```
  Virtual drivers (≤24) ── normal AC multiplayer session ──▶ they race EACH OTHER for real
                                                              (collidable, scored — specs/08)
        each client also runs:
  RaceSync feed ─▶ CSP Lua phantom layer ─▶ the REAL field shown as 3D cars (visual)
```

Virtual drivers race each other normally (collidable, networked, scored), **and** every
client independently renders the real field as CSP phantoms from the same broadcast feed.
Code 60 (specs/06) is enforced on the virtual field as before; phantoms simply reflect the
real cars slowing under Safety Car via their live data.

## 13.4 The Tier-B spike, step by step

**Goal:** drive ≥2 phantom cars in AC from a recorded RaceSync feed, placed correctly on
the SMSP track, moving smoothly, measured against the specs/09 latency/fidelity targets.

### Step 0 — Prereqs
- AC + **Custom Shaders Patch (CSP)** installed; Content Manager.
- The **acc-lua-sdk** / **acc-lua-internal `traffic`** tool as the reference for spawning
  and moving car meshes (the `BODY`-node technique).
- An SMSP track mod whose layout matches the configuration we calibrate to (specs/02 TBC-1).

### Step 1 — Get RaceSync data to the CSP Lua script (IPC)
CSP Lua cannot reliably open arbitrary UDP sockets, so bridge via a **shared memory-mapped
file** (recommended) that Lua reads each frame:

```
RaceSync ──UDP phantom packets──▶  ac-bridge  ──writes fixed-layout──▶  racesync_phantoms.bin
                                  (this repo)        binary frame              │
                                                                              ▼
                                                            CSP Lua reads it each frame
```

- Run the bridge (this repo): `python -m racesync.cli ac-bridge --file racesync_phantoms.bin`
  It listens for our phantom packets (UDP 9013) and writes the current world frame to the
  mmap file each update, in the **fixed binary layout** defined in
  [`src/racesync/injection/shm_bridge.py`](../src/racesync/injection/shm_bridge.py)
  (header: magic/version/count/flags/seq; then per-car `id,x,y,heading,speed,quality`).
- Feed it from a recording: `python -m racesync.cli spike --nmea-dir examples/nmea --use-ac`.
- The CSP Lua starter ([`tools/ac_companion/csp_phantoms/phantoms.lua`](../tools/ac_companion/csp_phantoms/phantoms.lua))
  reads the same layout. **Confirm the exact CSP Lua mmap/struct API** against the
  acc-lua-sdk when you wire it (the starter marks the call sites).

### Step 2 — Calibrate the coordinate transform (the crucial sub-task)
RaceSync positions are in our **SMSP track-plane metres** (specs/04); AC has its own world
origin/orientation/scale for the track mod. Solve a 2D **affine transform** once:
1. In AC, drive to 3+ known points on track (e.g. start/finish, two corner apexes), reading
   AC world coords via CSP Lua (`car.position`) and logging them.
2. Capture the **same** points in RaceSync coordinates (from the matching GPS trace / track
   frame `s`).
3. Solve scale + rotation + translation (least-squares) mapping RaceSync (x,y) → AC (x,z).
4. Bake the transform into the Lua script (or apply it in the bridge before writing).

Calibration quality **is** placement quality — budget real time here. (A surveyed SMSP
centreline, TBC-1, makes this exact.)

### Step 3 — Render & move phantoms
- In `phantoms.lua`, spawn N phantom car meshes (traffic-tool style: low-LOD body on a
  `BODY` node) and, each frame, set each phantom's transform from the mmap frame (after the
  Step-2 transform), interpolating between updates for smoothness.
- Heading from the packet orients the car; speed can drive wheel spin/animation if wanted.

### Step 4 — Measure (reuse the harness)
- **Latency:** the existing `InjectionHarness` already scores end-to-end latency. For a real
  verdict, timestamp a position at capture and again when the Lua frame applies it (write a
  Lua-side apply timestamp back into the mmap, or log it) and compare on one clock — vs the
  specs/09 targets (p50 ≤ 250 ms, p95 ≤ 500 ms).
- **Fidelity (visual):** smoothness (no teleport/strobe), placement (on the right part of
  track, within a car length with RTK data), and **phantom-count scaling toward 56**.
- **Code 60:** push a global packet (`code60=true`) and confirm the bridge sets the flag and
  the Lua reflects it (e.g. tints phantoms / shows a banner).

### Step 5 — Decision gate (specs/05 §5.4)
- **PASS** → Tier B is the injection mechanism; build out the production Lua + calibration
  and broadcast the feed to all virtual clients.
- **MARGINAL** (placement/latency borderline) → tune interpolation, calibration, feed rate.
- **FAIL** → fall back to **Strategy 3** (specs/05): no in-world phantoms; combined track-map
  overlay + full state/audio/scoring sync (already built). The event still runs.

## 13.5 Tier C (collidable) — documented, deferred

If visual phantoms prove insufficient and contactable cars are required:

- **Puppet clients:** run one AC client per phantom, each joining the MP session, each
  *driven* by an autopilot that chases the GPS path (specs/05 Strategy 2). Real, collidable,
  networked — but heavy (per-client CPU/GPU, ~one PC per few cars), and driving a client
  precisely from outside is non-trivial. Scope a small (2–4 car) proof before committing.
- **Modded `acServer` AI:** inject AI entries server-side (community-modded servers can add
  AI). Bound to AI splines and not designed for externally-authored lines; high risk.

Both are out of scope for the first spike; the gate in 13.4 decides whether they're worth
exploring.

## 13.6 What this repo already gives the spike

- **Feed:** `gen-nmea` (10-car SMSP field) + `examples/nmea/`; or live GPS via `UdpTelemetrySource`.
- **Pipeline:** ingestion → fusion → the **AC adapter** that emits the phantom packets.
- **Bridge:** `injection/shm_bridge.py` (+ `ac-bridge` CLI) — UDP packets → fixed mmap frame.
- **Receiver/visualizer:** `PhantomReceiver`, `racesync visualize` to sanity-check positions
  before AC.
- **Harness:** `InjectionHarness` for the latency verdict.
- **Lua starter:** `tools/ac_companion/csp_phantoms/phantoms.lua` (skeleton + the mmap layout
  and the calibration/API TODOs marked).

## 13.7 Risks specific to AC injection

| Risk | Mitigation |
|------|------------|
| CSP Lua mmap/struct API differs from the starter's assumptions | Confirm against acc-lua-sdk; the layout is isolated in `shm_bridge.py` + the Lua header so only one place changes |
| Coordinate calibration is off → cars beside/under the track | Step 2 least-squares from ≥3 points; verify with `visualize` first; pursue a surveyed centreline (TBC-1) |
| Phantoms don't appear in replays / aren't collidable | Accept for Tier B (visual); escalate to Tier C only if contact is required |
| Count scaling (toward 56) costs frame-rate | CSP traffic handles ~2000 cars cheaply; still measure FPS as N grows |
| Latency through bridge+Lua exceeds budget | Measure (Step 4); raise feed rate, interpolate, co-locate the bridge with the client |

## 13.8 Open items (to [`10`](10-delivery-plan-and-risks.md))

- **O-20** Confirm CSP Lua's shared-memory/struct read API and whether it can open UDP
  directly (would remove the bridge).
- **O-21** SMSP track mod choice + surveyed centreline for exact calibration (TBC-1).
- **O-22** Whether Tier B phantoms get colliders (local contact) or remain pass-through.

## Sources

- AC server UDP plugin protocol (read + admin; no position-set):
  [acudpclient](https://github.com/joaoubaldo/acudpclient),
  [Emperor Servers — UDP Plugins](https://wiki.emperorservers.com/assetto-corsa-server-manager/udp-plugins).
- CSP Lua SDK + traffic (spawn/move car meshes, `BODY` node, ~2000 cars):
  [acc-lua-sdk](https://github.com/ac-custom-shaders-patch/acc-lua-sdk),
  [acc-lua-internal `traffic`](https://github.com/ac-custom-shaders-patch/acc-lua-internal/tree/main/included-tools/traffic).
- AI-in-multiplayer limitation / spline traffic:
  [AssettoServer FAQ](https://assettoserver.org/docs/next/faq/),
  [OverTake — AI cars in MP](https://www.overtake.gg/threads/question-for-devs-modders-ai-cars-in-multiplayer-servers.265191/).
