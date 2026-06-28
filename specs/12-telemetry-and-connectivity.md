# 12 — Telemetry & Connectivity (car ⇄ RaceSync ⇄ sim)

This answers the practical wiring question: **how does a real car's position get from the
GNSS unit into the simulator?** It covers the links each car needs, why the RTK base is
*not* the path to the game server, and how to choose between Wi-Fi, cellular, and private
radio at Sydney Motorsport Park. It builds on the hardware in
[`11-gps-hardware-options.md`](11-gps-hardware-options.md) and the ingestion model in
[`04-data-feeds.md`](04-data-feeds.md).

## 12.1 The key idea: three independent links, two directions

Each car participates in up to **three separate links**. Keeping them distinct is the
whole answer to "are the RTK stations the link back to the game server?" — **no, they are
not.**

| Link | Direction | Purpose | Carries | Covered in |
|------|-----------|---------|---------|------------|
| **A. RTK corrections** | base → car (**down**) | make the car's fix accurate (cm) | RTCM3 correction stream | §12.3 |
| **B. Position telemetry** | car → RaceSync (**up**) | tell RaceSync where the car is | NMEA/UBX or a compact packet | §12.4 |
| **C. Race audio** | Race Control → driver (**down**) | one-way race-management voice | Zello `MRA-RMC` on the driver's phone | [`07`](07-audio-race-management.md) |

Link **A** is about *accuracy*; link **B** is about *getting the data back*. They flow in
**opposite directions** and exist for different reasons. A common confusion is to think the
RTK base "sends the car into the game" — it does not. The base only helps the car compute a
better position; that position then travels **up** link B to RaceSync.

## 12.2 The end-to-end data path (where the game server sits)

```
  ┌──────────────── IN EACH CAR ────────────────┐
  │  GNSS rover (F9R / UM982)                     │
  │   ▲ corrections (A)        position (B) ▼      │
  │   │                        companion MCU       │
  └───┼────────────────────────────┼──────────────┘
      │                            │
   RTK base                  uplink network
  (RTCM3, down)              (cellular / Wi-Fi / radio, up)
      │                            │
      ▼                            ▼
  ┌─────────────────── TRACKSIDE "RaceSync base" ───────────────────┐
  │  RTK base station  +  Telemetry gateway  +  Feed Ingestion (C1)  │
  │                         │ Position Model + Fusion (C1)            │
  └─────────────────────────┼───────────────────────────────────────┘
                            │  injection stream (C3)
                            ▼
                   ┌─────────────────┐      remote virtual drivers (≤24)
                   │  Sim / game host │◀──────────────────────────────
                   │  + AC companion  │
                   └─────────────────┘
```

**The cars never talk to the game server directly.** They send position **up to RaceSync
ingestion** (C1); RaceSync fuses it into the Position Model and **drives the simulator** via
the injection adapter (C3, [`05`](05-sim-injection-feasibility.md)). The sim/game host —
where the virtual drivers connect — receives *phantom car states from RaceSync*, not raw
GPS from cars. So the chain is:

> **car → uplink → RaceSync ingestion → fusion → injection → sim → virtual drivers.**

This matters because it means the uplink only has to reach the **RaceSync edge node**
(which can sit trackside), not the cloud sim host. RaceSync then forwards a clean, fused,
rate-controlled injection stream onward — far better than 56 cars each hammering the game
server.

## 12.3 Link A — RTK corrections (down)

Recap from [`11` §11.4](11-gps-hardware-options.md): **one local RTK base at SMSP**
broadcasts RTCM3 to every car rover (sub-km baseline → best accuracy, internet-independent).
Delivery options for the corrections themselves:

- **Over the same uplink network** as a downlink (e.g. an NTRIP caster the cars pull from
  over cellular/Wi-Fi). Simplest if the network is bidirectional.
- **A dedicated correction radio** (e.g. the base's own 900 MHz broadcast, or the LoRa radio
  built into units like the UM982/Torch). Independent of the telemetry path — preferred for
  resilience (losing telemetry doesn't lose accuracy, and vice-versa).

Corrections are **broadcast** (one stream, all cars), so they cost almost no bandwidth per
car and scale trivially to the whole field.

## 12.4 Link B — position telemetry (up): the real question

This is the link you asked about. Options, judged for SMSP (~3.9 km lap, up to 56 cars,
small high-rate packets):

| Option | Bandwidth | Latency | Range/coverage | Cost | Integration effort | Verdict |
|--------|-----------|---------|----------------|------|--------------------|---------|
| **4G/LTE per car** (SIM + modem) | ample | ~30–100 ms, variable; worse under event congestion | anywhere with coverage | per-SIM, modem/car | low | **Best pilot baseline.** Each car uploads independently to a cloud/edge collector. Watch congestion at a packed event. |
| **Private Wi-Fi mesh** (trackside APs) | high | low (~5–20 ms) | needs several APs to blanket the circuit; **roaming/handoff at racing speed is the hard part** | APs + cabling/power | medium–high | Good bandwidth, but covering 3.9 km and handing off fast-moving cars between APs is non-trivial. Not the easy win it sounds like. |
| **Private 900 MHz radio** (RFD900x-class, 915 MHz ISM AU) | **low** (~tens of kB/s shared) | low (~5–20 ms) | long, robust, whole circuit from one base | radios/car + base | medium | Robust and simple coverage, but **shared low bandwidth** is the catch — fine for a small field or ~5–10 Hz, tight for 56 cars at 25–50 Hz (see §12.5). |
| **LoRa** | very low | higher | very long | cheap | low | Only for coarse, low-rate position (a few Hz). Good fallback/overlay tier, not full-fidelity injection. |
| **Private LTE / CBRS** | ample | low | whole circuit, managed | high (infra) | high | The "proper" answer for a permanent installation; over-spec for a first event. |

### So, Wi-Fi or something similar?

- **Wi-Fi works but isn't the obvious best choice.** Blanketing a 3.9 km circuit needs
  multiple trackside access points and, crucially, **fast roaming** as a car at 200 km/h
  crosses cells — that handoff is where simple Wi-Fi struggles. Use it only if you already
  have good trackside AP coverage and tested roaming.
- **For a first event, 4G/LTE per car is the lowest-effort path** that reaches the whole
  circuit with enough bandwidth — each car just needs a modem/SIM and uploads to RaceSync.
  Its weakness is **shared public-network congestion** at a busy meeting, so measure latency
  early (it eats into the 250 ms injection budget, [`09` §9.1](09-non-functional-requirements.md)).
- **For reliability at full field/high rate, a private radio path** (900 MHz to a trackside
  base) avoids cellular dependence — at the cost of bandwidth (§12.5).

**Recommended approach:** start the pilot on **4G/LTE per car → cloud/edge UDP collector**;
in parallel, stand up a **trackside "RaceSync base"** (RTK base + telemetry gateway in one
place) and evaluate a **private 900 MHz/Wi-Fi uplink** for the production event. Treat the
uplink as a pluggable transport behind the existing `PositionSource` interface so it can
change without touching fusion/state/scoring.

## 12.5 Bandwidth & latency budget (do the numbers)

**Per-fix size:** a compact position packet is ~50–100 bytes (car id, time, lat/lon or x/y,
speed, heading, fix-quality, sequence). Raw NMEA is larger (~70–120 B/sentence).

**Aggregate (worst case, 56 cars):**

| Rate | Packets/s (56 cars) | Approx. throughput |
|------|---------------------|--------------------|
| 10 Hz | 560 | ~30–60 kB/s |
| 25 Hz | 1,400 | ~70–140 kB/s |
| 50 Hz | 2,800 | ~140–280 kB/s |

- **Cellular / Wi-Fi / private LTE:** trivially handle even 50 Hz × 56. Not a constraint.
- **900 MHz (RFD900x ~ up to ~250 kbit/s ≈ 31 kB/s, shared half-duplex):** enough for ~10 Hz
  across a **small** field, **not** 56 cars at 25–50 Hz. Mitigations: lower rate, multiple
  channels/base receivers, or reserve radio for a subset and cellular for the rest.

**Latency:** the uplink is part of the end-to-end injection budget (target ≤250 ms typical,
[`09`](09-non-functional-requirements.md)). Private radio/Wi-Fi add ~5–20 ms; cellular adds
~30–100 ms and is variable. Whatever is chosen, the Health Monitor (C7) measures per-source
freshness so a degrading uplink is visible, and dead-reckoning (C1) rides out brief gaps.

## 12.6 Transport & wire format

- **Transport: UDP, not TCP**, for position. Freshness beats completeness — a late-but-exact
  fix is worse than dropping it and using the next one (specs/04, specs/09 §9.6). Packets
  carry a **sequence number** so the receiver can discard stale/out-of-order data.
  (A management/MQTT channel over TCP is fine for non-real-time config/health.)
- **On-wire payload:** two supported forms into Feed Ingestion:
  1. **Raw NMEA** sentences (`$..GGA/RMC`) — simplest; the car forwards what the receiver
     emits. Parsed by `NmeaGpsSource` (already implemented).
  2. **Compact RaceSync telemetry packet** — a small JSON (or later binary) record carrying
     `car`, `t`, `lat/lon` (or `x/y`), `spd`, `hdg`, `q` (fix quality), `seq`. Decoded by the
     new `UdpTelemetrySource`. Preferred for bandwidth and because it carries the car id and
     fix quality explicitly.
- Both land as `RawFix` in the Position Model — the rest of the system is unchanged
  (specs/04 §4.4: swapping the transport changes fidelity, not correctness).

## 12.7 The trackside "RaceSync base" (convergence site)

Physically co-locate, at one trackside cabinet/site:

- the **RTK base station** (Link A source),
- the **telemetry gateway / UDP collector** (Link B sink),
- the **RaceSync edge node** (Feed Ingestion C1, Race State Engine C2, Operator Console C8).

This is the natural convergence point — and if you use a **bidirectional radio** (e.g. a
900 MHz network), the *same* radio site can broadcast corrections **down** and receive
telemetry **up**. That is the kernel of truth behind "are the RTK stations the link back?":
the **site** can host both, and one radio network can carry both directions — but the **RTK
correction function** and the **telemetry-return function** remain logically separate, and
**neither is the game server** (the edge node forwards to the sim host, §12.2).

## 12.8 Requirements

- **F-12-1** Position telemetry MUST reach RaceSync Feed Ingestion (the edge node), not the
  sim/game host directly; RaceSync forwards a fused injection stream to the sim.
- **F-12-2** The uplink MUST be a pluggable transport behind `PositionSource`; changing it
  MUST NOT require changes to fusion, state, or scoring.
- **F-12-3** Position transport SHOULD be UDP with per-packet sequence numbers; stale/out-of-
  order packets MUST be discardable.
- **F-12-4** Ingestion MUST accept both raw NMEA and the compact RaceSync telemetry packet.
- **F-12-5** RTK corrections (down) and position telemetry (up) MUST be able to run on
  independent links so loss of one degrades accuracy or freshness, not both.
- **F-12-6** Per-source uplink freshness MUST be observable by the Health Monitor (C7).

## 12.9 Open items (to [`10`](10-delivery-plan-and-risks.md))

- **O-17** Uplink choice for the production event (cellular vs private radio vs Wi-Fi),
  decided by a trackside coverage/latency test at SMSP.
- **O-18** Whether corrections ride the telemetry network (NTRIP) or a dedicated radio.
- **O-19** Binary telemetry packet format if bandwidth on a constrained link demands it.
- **TBC-2/TBC-3** (specs/02) X2 feed access and GPS hardware — gate the source mix.
