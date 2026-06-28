# 11 — GPS / GNSS Hardware Options

Concrete, affordable in-car positioning hardware that meets the Position-Model needs of
[`04-data-feeds.md`](04-data-feeds.md) and the fidelity/latency targets of
[`09-non-functional-requirements.md`](09-non-functional-requirements.md), specifically for
the **live car-injection** model ([`05`](05-sim-injection-feasibility.md)) where injected
cars must sit in roughly the right place at the right time.

Prices are **approximate, ex-tax, USD, as of June 2026** and vary by vendor/region — treat
them as sizing inputs, not quotes. Sources at the end.

## 11.1 What the spec demands of a unit

| Requirement | Target | Why |
|-------------|--------|-----|
| Update rate | **≥10 Hz, ideally 25–50 Hz** | At 200 km/h a car covers ~55 m/s: 10 Hz = 5.6 m between fixes, 25 Hz = 2.2 m, 50 Hz = 1.1 m. Higher rate = smoother injected motion (#04 §4.3, #09 §9.1). |
| Absolute accuracy | **≤2 m, cm-level with RTK** | Wheel-to-wheel injection needs the car on the correct part of the track, not just the correct corner (#09 §9.2). |
| Robustness to dropouts/vibration | **IMU sensor fusion (dead reckoning) preferred** | Race cars vibrate, brake hard, and pass under bridges/grandstands; fusion bridges short GNSS gaps so phantoms don't freeze/jump (#04 §4.3). |
| Heading | **Useful** (motion-derived or dual-antenna) | The sim needs car yaw to orient the phantom; dual-antenna gives true heading even at low speed. |
| Telemetry out | NMEA/UBX over serial/USB | Parsed by the existing `NmeaGpsSource` (`src/racesync/sources/gps_nmea.py`). |

Two things are **separate** from the unit choice and addressed in §11.4–11.5: **how RTK
corrections reach the car**, and **how position telemetry gets from the car to RaceSync**.

## 11.2 Candidate units

| Unit | GNSS engine | Max rate | RTK | IMU fusion | Heading | ~Price (board) | Notes |
|------|-------------|----------|-----|-----------|---------|----------------|-------|
| **u-blox ZED-F9R** breakout (SparkFun GPS-RTK Dead Reckoning; ArduSimple simpleRTK2B-F9R) | L1/L2, 4-constellation | **30 Hz** fused | ✓ (cm w/ corrections) | **✓ built-in ADR** (IMU + wheel ticks) | motion-derived | **~$200** | **Best all-round for a car.** Fusion rides out vibration/dropouts. u-blox notes F9R is tuned for asphalt road vehicles — circuit asphalt is in-domain, but validate under racing dynamics in the spike. |
| **Unicore UM982** dual-antenna (gnss.store / TOPGNSS bare board; Holybro H-RTK UM982) | All-band, all-constellation, **dual antenna** | **50 Hz** | ✓ (cm) | ✗ (module); some carriers add IMU | **✓ true dual-antenna heading** | **~$200 bare → ~$400–480 (Holybro kit)** | **Best rate + true heading.** Dual-antenna yaw is independent of motion (great for the sim). Needs two antennas mounted with a baseline; a bit more integration. |
| **u-blox ZED-F9P** breakout (ArduSimple simpleRTK2B Budget; SparkFun GPS-RTK2 / -SMA) | L1/L2, 4-constellation | **20 Hz** RTK | ✓ (cm) | ✗ | motion-derived | **~$155–275** | Proven, cheap, huge community/tooling. No fusion: degrades more in dropouts/high-dynamics than F9R. Good base-station choice too. |
| **RaceBox Mini S** | Multi-constellation | **25 Hz** | ✗ (no RTK) | ✓ (acc+gyro, logging) | motion-derived | **~$200** | **Plug-and-play fallback tier.** Self-contained, BLE, motorsport-app friendly. ~1–2.5 m typical (no corrections) → fine for leaderboard/coarse overlay, not tight injection. |
| **SparkFun RTK Torch** (Unicore UM980) | Quad-band, all-constellation | ~20 Hz (surveyor default 2 Hz) | ✓ (cm) | ✓ tilt | — | **~$2,150** | Survey-grade, waterproof, on-board LoRa. **Over-spec and over-budget for a fleet**; listed for completeness. |

### Reading

- **Default pick: ZED-F9R** — at ~$200 it hits ≥25 Hz, cm-with-RTK, **and** has the IMU
  sensor fusion that matters most in a vibrating, hard-braking race car. Best
  robustness-per-dollar.
- **Step-up pick: Unicore UM982** — when you want **50 Hz and true heading** (dual
  antenna) for the cleanest phantom orientation, at a modest price premium and a little
  more mounting/integration.
- **Budget/pilot pick: RaceBox Mini S** — cheapest, self-contained, but **no RTK**; use for
  a low-cost pilot, the coarse-overlay (Strategy 3) tier, or cars where cm accuracy isn't
  justified. Plan to graduate to RTK for real injection.
- **F9P** is the value RTK option if fusion isn't needed and is the natural **base-station**
  module.

## 11.3 Mapping rate to injection fidelity

| Rate | Gap @ 200 km/h | Suitable for |
|------|----------------|--------------|
| 10 Hz | 5.6 m | minimum; leaderboard + coarse overlay |
| 25 Hz | 2.2 m | good injection with interpolation/fusion |
| 50 Hz | 1.1 m | best; tight wheel-to-wheel phantom fidelity |

Combine **rate** (smoothness) with **RTK** (absolute accuracy) and **IMU fusion**
(continuity through gaps). The recommended targets — **25–50 Hz + RTK-fixed + fusion** —
are met by the F9R (30 Hz, fusion) and UM982 (50 Hz, dual-antenna heading).

## 11.4 RTK corrections — delivery at a fixed circuit

RTK needs a correction stream (RTCM3) from a reference of known position. At a **single
fixed venue** this is easy and cheap, and one base serves the whole field:

- **Recommended: one local RTK base station at SMSP**, broadcasting RTCM3 to all car
  rovers. The base→car baseline is **< 1 km**, which gives the **best possible accuracy**
  (short baseline minimises atmospheric error) and is **internet-independent** — important
  given trackside connectivity is unreliable (#01 A3, #09 §9.6).
  - Base hardware: a ZED-F9P board + survey/multi-band antenna on a known point
    (**~$300–500 one-off**). The same RTCM3 stream feeds every rover.
  - Distribution of corrections to cars: see §11.5 (can share the telemetry link, or use a
    dedicated radio / on-board LoRa as some units provide).
- **Alternative: NTRIP over cellular** from an Australian CORS/network-RTK provider. No
  base hardware, but depends on cellular coverage/throughput at the circuit — acceptable as
  a backup, not the primary at a dense event.

> A surveyed base point also gives RaceSync the **track frame reference** (#04 §4.2) for
> free — the base coordinates anchor the local projection used for map-matching.

## 11.5 Two links per car — don't conflate them

Each car needs **two** data paths; keep them separate in the design:

1. **Corrections DOWN (base → car):** RTCM3 to the rover. Options: a private radio
   (900 MHz/2.4 GHz), on-board LoRa (UM982/Torch include it), or piggy-backed on the
   telemetry link below.
2. **Position UP (car → RaceSync edge):** the NMEA/UBX position stream to Feed Ingestion
   (#03/#04). Bandwidth is small — ~50–100 B/fix → ~1–2.5 kB/s/car at 10–25 Hz; even 56
   cars is ≲150 kB/s aggregate. Options:
   - **4G/LTE modem per car** — simplest; watch trackside cellular congestion.
   - **Private 900 MHz / 2.4 GHz / WiFi-mesh** — avoids cellular dependency; preferred for
     reliability at a busy venue.
   - **LoRa** — robust and long-range but low bandwidth; fine for ~5–10 Hz coarse position,
     tight for 25–50 Hz full-rate.

Each car therefore carries: GNSS unit + antenna(s), a small companion MCU/SBC
(ESP32 / Teensy / RPi Zero) to read the receiver and drive the uplink (the RaceBox is the
exception — it's self-contained with BLE), power from the car's 12 V, and an enclosure.

## 11.6 Indicative fleet cost

| Tier | Per-car BOM | 24 cars | 56 cars |
|------|-------------|---------|---------|
| **RTK + fusion (F9R)** | F9R ~$200 + multi-band antenna ~$40 + companion MCU ~$25 + uplink (LTE/radio) ~$40 + enclosure/wiring ~$30 ≈ **$335** | ~$8k | ~$19k |
| **RTK + 50 Hz heading (UM982)** | board ~$250 + 2× antenna ~$80 + MCU ~$25 + uplink ~$40 + enclosure ~$30 ≈ **$425** | ~$10k | ~$24k |
| **Budget no-RTK (RaceBox Mini S)** | self-contained ~$200 (+ uplink bridge if not phone-tethered) ≈ **$200–240** | ~$5k | ~$13k |
| **Shared infrastructure** | 1× RTK base ~$400 + corrections radio ~$150 | — | — |

(Excludes labour, spares, and any existing team telemetry that could carry the uplink.)

## 11.7 Recommended approach

1. **Pilot / feasibility spike (#05, Phase 1):** buy **2–4× ZED-F9R units + 1 RTK base**.
   Validate, on a real car at SMSP: achieved rate, RTK-fix reliability under racing
   dynamics, dropout behaviour (fusion), and **end-to-end injection latency** against the
   #05/#09 targets. This is small spend to de-risk the whole concept.
2. **If 50 Hz / true heading proves necessary** for phantom fidelity, evaluate **UM982
   dual-antenna** in parallel.
3. **Scale** the chosen unit to the field once the spike passes; keep **RaceBox Mini S** as
   a documented budget/fallback tier for the coarse-overlay path or cost-sensitive cars.
4. **Corrections:** standardise on **one local RTK base broadcasting RTCM3**, with NTRIP
   cellular as backup.
5. Treat the GNSS unit as a **pluggable source** behind `PositionSource` (already
   implemented) — the receiver can change without touching fusion, state, or scoring.

## 11.8 Requirements

- **F-11-1** In-car units MUST output ≥10 Hz (target 25–50 Hz) position over a parseable
  protocol (NMEA/UBX) consumable by `NmeaGpsSource`.
- **F-11-2** The system MUST support RTK-corrected units delivering cm-level accuracy via a
  local base (RTCM3), and MUST degrade gracefully to non-RTK accuracy (#04 F-04-5).
- **F-11-3** The recommended in-car unit SHOULD provide IMU sensor fusion or dual-antenna
  heading for robustness/orientation.
- **F-11-4** Corrections-down and position-up links MUST be independent so loss of one
  degrades fidelity, not correctness.
- **F-11-5** Unit selection MUST be validated against the #05 injection latency/fidelity
  targets in the Phase-1 spike before fleet purchase.

## 11.9 Open items (to #10)

- **TBC-3** (#02) Confirm whether any GPS units are already fitted, and their rate/accuracy.
- **O-15** Final unit choice + corrections/uplink transport, decided by the Phase-1 spike.
- **O-16** Whether to standardise one unit fleet-wide or run mixed tiers (RTK vs RaceBox).

## Sources

- [u-blox ZED-F9R product page](https://www.u-blox.com/en/product/zed-f9r-module) and
  [SparkFun GPS-RTK Dead Reckoning ZED-F9R hookup guide](https://learn.sparkfun.com/tutorials/sparkfun-gps-rtk-dead-reckoning-zed-f9r-hookup-guide/all)
  (30 Hz fused, ADR sensor fusion, 100 Hz IMU, asphalt-road domain note).
- [u-blox ZED-F9P module](https://www.u-blox.com/en/product/zed-f9p-module) /
  [ArduSimple simpleRTK2B Budget](https://www.ardusimple.com/product/simplertk2b/) /
  [SparkFun GPS-RTK-SMA ZED-F9P](https://www.sparkfun.com/sparkfun-gps-rtk-sma-breakout-zed-f9p-qwiic.html)
  (20 Hz RTK; ~$155–275).
- [Unicore UM982 (dual-antenna, 50 Hz)](https://en.unicore.com/products/um982/) /
  [Holybro H-RTK UM982](https://holybro.com/products/h-rtk-unicore-um982) /
  [GNSS Store UM982 boards](https://gnss.store/collections/unicore-um982) (~$200–480).
- [SparkFun RTK Torch (UM980, LoRa)](https://www.sparkfun.com/sparkfun-rtk-torch.html) (~$2,150; survey-grade).
- [RaceBox Mini S (25 Hz, no RTK)](https://www.racebox.pro/products/racebox-mini-s).
- RTK corrections / base vs NTRIP & baseline-vs-accuracy:
  [ArduSimple GNSS/RTK base station](https://www.ardusimple.com/gnss-rtk-base-station/),
  [Robota: NTRIP vs radio](https://www.robota.us/post/rtk-gps-base-station-setup-ntrip-vs-radio-configurations-explained),
  [Emlid: RTK corrections explained](https://blog.emlid.com/rtk-corrections-explained-from-base-station-to-ntrip-service/).
