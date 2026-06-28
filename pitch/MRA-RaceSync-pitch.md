---
marp: true
theme: default
paginate: true
size: 16:9
backgroundColor: "#0b0f14"
color: "#e8eef5"
style: |
  section { font-family: "Segoe UI", Helvetica, Arial, sans-serif; font-size: 26px; }
  h1 { color: #6cc6ff; }
  h2 { color: #ffd24d; }
  strong { color: #9ff0a3; }
  a { color: #6cc6ff; }
  table { font-size: 22px; }
  section.lead { text-align: center; }
  footer { color: #5b6b7a; }
---

<!-- _class: lead -->
# RaceSync
## One race. Two worlds.

**Bringing a global virtual grid to the Viola Private Wealth Sydney 300 —
racing the real field, live, under one MRA permit.**

A proposal for **Terry & Motor Racing Australia**

---

## The shift happening around us

- **Sim racing is now mainstream** — tens of millions of players, huge online audiences,
  and a generation of fans who compete from home.
- **Real-world club motorsport** fights rising costs, ageing grids, and limited reach.
- These two worlds barely touch — yet they share the same circuits, the same rules,
  and the same love of racing.

> **What if your event could run both at once — and own the bridge between them?**

---

## The idea, in one line

A field of **real cars** races the Sydney 300 at Sydney Motorsport Park.

A field of **remote sim racers** races **the same race, at the same time**, against live
digital twins of your real cars — scored as their **own class**, under the **same MRA
permit**.

**RaceSync** is the technology that makes the two fields one event.

---

## How it works (no new burden on your operation)

| Real world (you already run this) | RaceSync adds |
|-----------------------------------|---------------|
| MyLaps timing & transponders | reads your live timing/GPS |
| Zello **MRA-RMC** race-management channel | relays your *one* race-control voice to virtual drivers too |
| Safety Car procedures | becomes **Code 60** for the virtual field, automatically |
| Race Control & Clerk of Course | one extra operator console **beside** Race Control |

The real cars are streamed into the simulator as moving cars. Virtual drivers see them,
race them, and hear your officials — **one race, one set of rules**.

---

## What's in it for MRA

- **New revenue** — entry fees from a virtual grid, plus fresh **sponsor inventory**
  (virtual-class naming, in-sim branding, streaming overlays).
- **A bigger audience** — your event reaches the global sim-racing community and streams
  natively to Twitch/YouTube.
- **A standout story** — a **hybrid real/virtual enduro is genuinely novel**; it earns
  media and sets MRA apart from every other organiser.
- **Future-proofing** — whether the Sydney 300 stays physical, goes hybrid, or one day runs
  virtual-only, **RaceSync owns that transition** for you.

---

## Safe and fair by design

- **Virtual cars can never touch a real car or driver** — the crossover is one-way: sim
  racers see the real field, the real field races as normal.
- **Safety Car → Code 60**: when you neutralise the real race, the virtual field slows to
  60 km/h, no overtaking — fairness preserved on both sides.
- **Separate class, transparent scoring** — real and virtual cars are timed and classified
  independently, with a full audit trail; your official MyLaps result is never overridden.
- **Timed finish** — virtual cars take the chequer the instant your real leader completes
  300 km, so both fields finish together.

---

## This isn't a concept deck — it already runs

- A **working software platform** is built and tested today: live timing/GPS ingestion,
  race-state sync (green / Code 60 / timed finish), the race-audio bridge, and combined
  real-vs-virtual scoring — **100+ automated tests, continuous integration**.
- We can already **simulate the full Sydney 300 field** and drive it into a simulator.
- **Honest about the hard part:** putting real cars *inside* the sim is the frontier we're
  validating now — and there's a **guaranteed fallback** (a synced virtual race + live
  combined timing/track-map) so **the event is never hostage to unproven tech.**

---

## The driver & fan experience

- Virtual drivers race **collidable** digital twins of your real cars — real wheel-to-wheel,
  not ghosts (precision scales with RTK GPS).
- Everyone hears **the same Race Control** — your `MRA-RMC` voice, in their headset.
- A **combined live timing screen** and track map show both fields together — ready-made
  **broadcast** content.

---

## Low-risk rollout

1. **Pilot (off-track):** prove the data path on recorded laps — no event impact. *(done / in progress)*
2. **Test day at SMSP:** a few cars fitted with GPS; validate accuracy & latency on the real circuit.
3. **Dress rehearsal:** small virtual grid against a practice session.
4. **Event:** virtual class runs alongside the Sydney 300, scored under the permit.

At every step there's a **working fallback**, so we only ever *add* to your event.

---

## What we'd need from MRA

- **Your blessing to run a pilot** around the Sydney 300.
- Access, on commercial terms, to: the **MyLaps X2 timing feed**, the **`MRA-RMC` Zello
  channel**, and a **test session** at SMSP.
- A joint conversation with **Motorsport Australia** about permitting a concurrent virtual
  class and the Code 60 procedure.

We bring the technology, the build, and the operating crew.

---

<!-- _class: lead -->
## The Sydney 300, reimagined

**Same circuit. Same rules. Same race control.
A grid that now spans the world.**

Let's run a pilot and show what a hybrid Sydney 300 looks like.

*RaceSync — one race, two worlds.*
