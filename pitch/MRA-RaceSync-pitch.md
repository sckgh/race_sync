---
marp: true
theme: default
paginate: true
size: 16:9
backgroundColor: "#111418"
color: "#eef2f6"
footer: "Motor Racing Australia — NSW's premier motor racing series"
style: |
  /* ---- MRA brand variables: drop in exact hex/logo from motorrace.com.au ---- */
  /* --mra-red placeholder; --virtual cyan tells the real-vs-virtual story */
  :root { --mra-red:#e2231a; --virtual:#2fb8ff; --gold:#ffd24d; --muted:#8a98a6; }
  section { font-family: "Segoe UI", Helvetica, Arial, sans-serif; font-size: 25px;
            background: linear-gradient(160deg,#111418 0%,#15191f 100%); }
  h1 { color: var(--mra-red); }
  h2 { color: #ffffff; border-left: 6px solid var(--mra-red); padding-left: 14px; }
  strong { color: var(--virtual); }
  em.real { color: var(--mra-red); font-style: normal; font-weight: 700; }
  a { color: var(--virtual); }
  table { font-size: 21px; }
  footer { color: var(--muted); font-size: 14px; }
  section.lead { text-align: center; }
  section.lead h1 { font-size: 60px; }
---

<!-- _class: lead -->
# RaceSync
## One race. Two worlds.

**A global virtual grid, racing your real field — live, under one MRA permit.**

Trial it at the <em class="real">Wakefield 300</em>. Scale it to the **Sydney 300**.

###### A proposal for Terry & Motor Racing Australia

---

## The shift happening around us

- **Sim racing is now mainstream** — tens of millions of players, big online audiences,
  a generation who compete from home.
- **Club motorsport** fights rising costs, ageing grids, and limited reach.
- They share the same circuits, the same rules, the same love of racing — but barely touch.

> **MRA can own the bridge between them — and be first to do it.**

---

## The idea, in one line

Your <em class="real">real SuperTT field</em> races the enduro at the circuit.

A field of **remote sim racers** races **the same race, at the same time**, against live
digital twins of your real cars — scored as their **own class**, under the **same MRA
permit**.

**RaceSync** is the technology that makes the two fields one event.

---

## How it works — no new burden on your operation

| You already run this | RaceSync adds |
|----------------------|---------------|
| MyLaps timing & transponders | reads your live timing / GPS |
| Zello **MRA-RMC** race-management channel | relays your *one* race-control voice to virtual drivers too |
| Safety Car procedures | becomes **Code 60** for the virtual field, automatically |
| Race Control & Clerk of Course | one extra operator console **beside** Race Control |

Real cars stream into the simulator as moving cars. Virtual drivers see them, race them,
and hear your officials — **one race, one set of rules.**

---

## What's in it for MRA

- **New revenue** — entry fees from a virtual grid, plus fresh **sponsor inventory**
  (virtual-class naming, in-sim branding, streaming overlays).
- **A bigger audience** — your events reach the global sim-racing community and stream
  natively to Twitch / YouTube.
- **A season, not a one-off** — a virtual class can run across **all 8 rounds and the three
  300 km enduros** (Wakefield 300, Shelley 300, Sydney 300).
- **A standout story** — a hybrid real/virtual enduro is **genuinely novel**; it earns media
  and sets MRA apart from every other organiser.

---

## Safe and fair by design

- **Virtual cars can never touch a real car or driver** — the crossover is one-way: sim
  racers see the real field; your real field races as normal.
- **Safety Car → Code 60** — when you neutralise the real race, the virtual field drops to
  60 km/h, no overtaking. Fairness preserved on both sides.
- **Separate class, transparent scoring** — real and virtual cars are timed and classified
  independently, with a full audit trail; your official MyLaps result is never overridden.
- **Timed finish** — virtual cars take the chequer the instant your real leader completes
  the distance, so both fields finish together.

---

## This isn't a concept — it already runs

- A **working, tested platform** today: live timing/GPS ingestion, race-state sync
  (green / Code 60 / timed finish), the race-audio bridge, and combined real-vs-virtual
  scoring — **100+ automated tests, continuous integration.**
- We can already **simulate a full SuperTT field** and drive it into a simulator.
- **Honest about the frontier:** putting real cars *inside* the sim is what we're validating
  now — with a **guaranteed fallback** (a synced virtual race + live combined timing and
  track-map), so **the event is never hostage to unproven tech.**

---

## The driver & fan experience

- Virtual drivers race **collidable** digital twins of your real cars — real wheel-to-wheel,
  not ghosts (precision scales with RTK GPS).
- Everyone hears **the same Race Control** — your `MRA-RMC` voice, in their headset.
- A **combined live timing screen** and track map show both fields together —
  ready-made **broadcast** content for the stream.

---

## Trial it at the Wakefield 300

The 2026 calendar is the perfect proving ground — low stakes first, flagship last:

| Step | Event | When | Role |
|------|-------|------|------|
| **Trial** | <em class="real">Wakefield 300</em> · One Raceway | 28 Feb – 1 Mar 2026 | first live run, a few GPS-fitted cars |
| Iterate | **Shelley 300** + selected rounds | across the season | refine, grow the virtual grid |
| **Flagship** | **Sydney 300** · SMSP | season showcase | full hybrid event, broadcast |

You've **already aligned with Motorsport Australia for 2026** — so the sanctioning
conversation for a virtual class starts from an existing relationship, not a cold call.

---

## Low-risk rollout

1. **Pilot (off-track):** prove the data path on recorded laps — zero event impact. *(in progress)*
2. **Wakefield 300 test:** a few cars fitted with GPS; validate accuracy & latency on a real circuit.
3. **Dress rehearsal:** a small virtual grid against a practice session.
4. **Event:** the virtual class runs alongside the enduro, scored under the permit.

At every step there's a **working fallback** — we only ever *add* to your event.

---

## What we'd need from MRA

- **Your blessing to run the Wakefield 300 trial.**
- Access, on commercial terms, to: the **MyLaps X2 timing feed**, the **`MRA-RMC` Zello
  channel**, and a **test session**.
- A joint conversation with **Motorsport Australia** about permitting a concurrent virtual
  class and the Code 60 procedure.

We bring the technology, the build, and the operating crew.

---

<!-- _class: lead -->
## NSW's premier series — now racing two worlds

**Same circuits. Same rules. Same race control.
A grid that spans the globe.**

Let's run the Wakefield 300 trial and show what a hybrid MRA enduro looks like.

*RaceSync — one race, two worlds.*
