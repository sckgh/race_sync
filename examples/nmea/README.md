# Generated NMEA 0183 test data

Sample GPS data for testing the RaceSync ingestion → fusion → injection chain (and the
Assetto Corsa companion during the Phase-1 spike) without a car or a live receiver.

Regenerate / customise with:

```bash
python -m racesync.cli gen-nmea --cars 10 --rate 10 --duration 60 --out examples/nmea
```

## What's here

- `car_01.nmea` … `car_10.nmea` — one file per car, the `$GxGGA` + `$GxRMC` sentence
  stream that car's GNSS receiver would emit. Real SMSP-anchored latitude/longitude,
  RTK-fixed quality (GGA field = 4), speed-over-ground and course-over-ground, valid
  `*HH` checksums.
- `combined.timeline.txt` — all cars interleaved, each line prefixed `‹t› ‹car›` for
  inspection / a single time-ordered log.

## Field

10 cars at distinct speeds (~162–214 km/h), staggered on a grid near start/finish, each
with a mild cornering speed variation, lapping an SMSP-anchored ~3.896 km centreline.

> The track here is a smooth synthetic loop anchored at SMSP's real coordinates — good
> enough to produce plausible lat/lon traces. Swap in a surveyed SMSP centreline
> (`TrackFrame.from_geojson_line`) when available (specs/02 TBC-1).

## Feeding it into RaceSync

```python
from pathlib import Path
from racesync.sources.gps_nmea import NmeaGpsSource
from racesync.simgen import make_smsp_track
from racesync.fusion import Fusion

track = make_smsp_track()
streams = {f"{i:02d}": Path(f"examples/nmea/car_{i:02d}.nmea").read_text().splitlines()
           for i in range(1, 11)}
fusion = Fusion(track)
for fix in NmeaGpsSource(streams).stream():
    fusion.on_fix(fix)
print(fusion.order())   # most-advanced car first
```

For the car → RaceSync uplink path (UDP), wrap each sentence in the compact telemetry
packet via `racesync.sources.udp.encode_telemetry_packet`, or send raw NMEA to a
`UdpTelemetrySource.listen(...)` configured with that car's id (specs/12).
