# Glossary

Terms, acronyms, and conventions used across the RaceSync specs.

## Domain & sanctioning

| Term | Meaning |
|------|---------|
| **MA** | Motorsport Australia — national sanctioning body. The event runs under an MA permit; both real and virtual fields are intended to be permitted. |
| **CRSR** | Circuit Race Standing Regulations — MA's standing rules referenced by the event's Special Regulations (e.g. rolling start = CRSR 5.5). |
| **NCR** | National Competition Rules — MA's overarching rulebook. |
| **Special Regulations** | The event-specific rules document (the Viola Private Wealth Sydney 300 regs) — the authoritative source for race format. |
| **Clerk of the Course / Stewards / Race Control** | Officials who run and adjudicate the race. RaceSync's operator console sits alongside Race Control, not in place of it. |
| **Scrutineering** | Technical/safety inspection of cars and equipment. |

## The event

| Term | Meaning |
|------|---------|
| **SMSP** | Sydney Motorsport Park, Eastern Creek, NSW. |
| **Gardner GP** | The full ~3.9 km SMSP circuit configuration most consistent with 77 laps × ≈3.896 km = 300 km. **To be confirmed** against the Supplementary Regulations. |
| **Sydney 300** | The Viola Private Wealth Sydney 300 — 300 km / 77 lap race, max 56 cars, multi-driver. |
| **Division (A–E)** | Performance class assigned by qualifying lap time; sets the Compulsory Pit Stop requirement. Distinct from the real/virtual *class* split RaceSync adds. |
| **CPS** | Compulsory Pit Stop — minimum number/duration of pit stops per division. |
| **CPS Window** | Period during which CPS must be served (leader's lap 10 → leader's lap 65). |

## Timing & telemetry

| Term | Meaning |
|------|---------|
| **MyLaps** | Timing/transponder vendor used at the event. |
| **Transponder** | In-car timing device detected by track loops; gives crossings, lap and sector times. |
| **MyLaps Driver ID** | System identifying which driver is in a multi-driver car (used so cars need not nominate a starting driver). |
| **X2** | MyLaps' connected timing platform; can expose a live timing data feed (loops, passings, lap/sector times). |
| **Passing / crossing** | A transponder detection event at a timing loop. |
| **GPS feed** | Continuous latitude/longitude (+ optional speed/heading) position stream from an in-car GPS unit, if available — distinct from loop-based timing. |
| **Position model** | RaceSync's internal representation of where a car is on track (see [`04-data-feeds.md`](04-data-feeds.md)). |

## Simulation

| Term | Meaning |
|------|---------|
| **Sim / simulator** | The racing simulation hosting the virtual field (candidate platforms compared in #05). |
| **iRacing** | Subscription online sim; laser-scanned SMSP; **read-only** SDK — cannot spawn externally-driven cars. |
| **AC / ACC** | Assetto Corsa / Assetto Corsa Competizione. AC (original) is highly moddable. |
| **rF2 / LMU** | rFactor 2 / Le Mans Ultimate — share an internals plugin SDK. |
| **Injection** | Rendering a real car as a moving car inside the sim, driven by its live position data. |
| **Phantom / puppet car** | A sim entity representing a real car, whose world position is authored by RaceSync rather than by a human or the sim AI. |
| **Code 60** | Full-course speed restriction to 60 km/h with no overtaking — the virtual-field analogue of a real Safety Car period. |
| **Shared memory / SDK telemetry** | The sim's API for reading live session/car state (most sims) and, on some, sending limited control commands. |

## Audio & comms

| Term | Meaning |
|------|---------|
| **Race Receiver** | One-way receive-only radio worn by real drivers for Race Control messages. |
| **Zello** | Push-to-talk app. The event runs an official one-way channel `MRA-RMC`. |
| **MRA-RMC** | The event's official Zello race-management channel (one-way: Race Control → participants). |
| **Audio bridge** | RaceSync component relaying `MRA-RMC` into virtual drivers' audio. |

## Conventions

- **Speeds** in km/h, **distances** in km/m, **lap/sector times** as `M:SS.ssss` (e.g. `1:38.0000`).
- **Latency** in milliseconds (ms), measured end-to-end unless stated.
- **MUST / SHOULD / MAY** follow RFC 2119 sense in requirement statements.
- **Real field** = physical cars; **virtual field** = sim cars; **hybrid race** = both, concurrent.
