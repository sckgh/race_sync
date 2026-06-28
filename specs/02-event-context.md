# 02 — Event Context (SMSP / Sydney 300)

Facts the system must honour, derived from the **2026 Viola Private Wealth Sydney 300
Special Regulations** and SMSP circuit knowledge. Citations are to the regulation article
numbers. Items marked **(TBC)** need confirmation from the Supplementary Regulations or the
organiser before build.

## 2.1 The race at a glance

| Attribute | Value | Source |
|-----------|-------|--------|
| Distance | **300 km** | Art. 2.1 |
| Laps | **77** | Art. 2.1 |
| Implied lap length | ≈ **3.896 km** (300 / 77) | derived |
| Circuit | **Sydney Motorsport Park** — config assumed **Gardner GP** **(TBC)** | Art. 2.1 + derived |
| Max field | **56 cars** | Art. 1.2 |
| Drivers per car | **1, 2, or 3** | Art. 2.1 |
| Eligible cars | SuperTT (excl. ExtremeTT): Production Cars/Sports, Improved Production, BMW E30/E36, Porsche 944, MX-5, Excel, Pulsar | Art. 2.1 |
| Max lap pace | No lap faster than **1:38.000** all weekend | Art. 2.3, 14.3 |
| Start | **Rolling start**, CRSR Art. 5.5 | Art. 8.1 |
| Formation speed | 75–85 km/h; start signal = red lights extinguished | Art. 8.7–8.11 |

These drive RaceSync's race model: **77 laps is the real-race trigger for the virtual timed
finish**, lap length feeds the position model, and the rolling start defines how both
fields go green together (#06).

## 2.2 Divisions and Compulsory Pit Stops (CPS)

Divisions are set by fastest qualifying lap (Art. 14.1) and determine CPS obligations
(Art. 15.1). These matter to RaceSync because **the virtual field's race format and any
virtual pit/stop rules should be defined deliberately against this backdrop** (a v1
decision: see open question O-7 in #10 — does the virtual class have its own stop rules?).

| Division | Qualifying lap time | CPS requirement |
|----------|---------------------|-----------------|
| A | 1:38.0000–1:41.9999 | 2 × 5 min |
| B | 1:42.0000–1:45.9999 | 1 × 5 min + 1 × 2.5 min |
| C | 1:46.0000–1:49.9999 | 1 × 5 min |
| D | 1:50.0000–1:53.9999 | 1 × 5 min |
| E | 1:54.0000 and slower | 1 × 5 min |

- **CPS Window:** opens when the leader starts lap 10, closes when the leader starts lap 65
  (Art. 15.3). Indicated by siren + Pit Open/Closed board.
- **Safety Car does not extend the CPS Window** (Art. 15.5) and CPS **may** be served under
  Safety Car if pit lane is open (Art. 15.6). RaceSync's Code 60 mapping must not imply a
  different pit rule for the real field.
- The **leader's lap count** (Art. 15.3) is a first-class signal RaceSync needs from timing
  — it gates the CPS window *and* the race finish.

## 2.3 Safety Car

| Rule | Detail | Source |
|------|--------|--------|
| Operation | Per CRSR | Art. 11.1.1 |
| Lap counting | **All laps under Safety Car count as race laps** | Art. 11.1.2 |

Implication for RaceSync: when the real race is under Safety Car, the virtual field goes to
**Code 60** but **laps still count** in both worlds — the virtual race is not paused, it is
neutralised. The timed finish still references real-leader lap completion. See #06.

## 2.4 Race-management communications (the audio backbone)

The event already runs a one-way race-management comms stack RaceSync will reuse rather
than replace:

| Element | Detail | Source |
|---------|--------|--------|
| Race Receivers | Strongly recommended for all drivers; used to advise safety issues, **Safety Car deployment**, emergency vehicles, etc. | Art. 10.1–10.2 |
| Official Zello channel | **`MRA-RMC`** — Team Managers, Pit Crew, Drivers may connect | Art. 10.4 |
| Mirroring | **All Race Receiver transmissions are also sent on Zello `MRA-RMC`** | Art. 10.5 |
| Direction | **One-way**: Race Control/Organiser → participants. Others must not transmit unless authorised | Art. 10.7 |
| Relay allowed | Teams may relay Race Control messages to cars | Art. 10.9 |

This is why the audio design (#07) bridges **Zello `MRA-RMC`**: it is already the
authorised, mirrored, one-way superset of everything broadcast to the real field.

## 2.5 Identity & timing devices

| Element | Detail | Source |
|---------|--------|--------|
| Transponder | Every car must carry a functioning timing device at all times | Art. 13.1 |
| Failure handling | Non-registration for 3 consecutive laps → defined replacement procedure | Art. 13.2 |
| MyLaps Driver ID | Cars so fitted need not nominate a starting driver; others SMS the Chief Timekeeper | Art. 6.1–6.2 |
| Driver ID harness | MyLaps Driver ID wiring harness available from Eldee Timing ($90) | Art. 13.5 |

Implications for RaceSync:
- **Car identity** in our system keys off the **transponder/MyLaps ID**; **driver identity**
  (for multi-driver cars) keys off **MyLaps Driver ID** where present.
- RaceSync must tolerate **transponder dropouts** (Art. 13.2 scenario) — a car can go
  unseen for up to 3 laps before official action. The position model must dead-reckon or
  visibly degrade an injected car during such gaps (#04, #09).

## 2.6 Start procedure detail (for green-flag sync)

Rolling start specifics that the virtual start must mirror (Art. 8):

- Cars released from pit lane in grid order; form up 2×2; must be in formation **before
  Turn 9** (Art. 8.8).
- Official vehicle pulls off; field controlled by pole car at 75–85 km/h (Art. 8.10).
- **Start = red start lights extinguished** (Art. 8.11); green flag if lights fail (8.12).

RaceSync needs a crisp **"green" event** from Race Control to release the virtual field in
sync — captured as an operator action and/or a detected timing transition (#06).

## 2.7 Penalties relevant to timing/scoring

Penalties are post-applied by the Chief Timekeeper as lap penalties or served as
drive-throughs (Art. 29.1). RaceSync's results view (#08) for the **real** field must be
able to **display official penalties as applied** (it does not compute them) so combined
results stay consistent with the official classification. Virtual-class penalties are a
separate, RaceSync-defined matter (open question O-8, #10).

## 2.8 Facts to confirm before build (TBC register)

| Ref | Item | Why it matters |
|-----|------|----------------|
| TBC-1 | Exact SMSP **circuit configuration** (Gardner GP vs other) | Determines sim track/mod and position model geometry |
| TBC-2 | Whether a **MyLaps X2 live data feed** is available to RaceSync at the event, and on what terms | Gates the primary data path (#04) |
| TBC-3 | Whether **true in-car GPS** units will be fitted, at what rate/accuracy | Determines injection fidelity ceiling (#04, #05) |
| TBC-4 | **Estimated race duration** (for timed virtual finish planning) and expected SC frequency | Sizing, driver-stint planning |
| TBC-5 | MA's position on **permitting a concurrent virtual class** and Code 60 procedure | Sanctioning viability (#01 A1) |
| TBC-6 | Access/credentials for **Zello `MRA-RMC`** as a relay source | Audio bridge (#07) |
