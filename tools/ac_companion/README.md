# RaceSync Phantoms — Assetto Corsa companion app

The sim-side endpoint of the injection path. It receives phantom-car packets from RaceSync
over UDP and draws them as an in-AC overlay (a 2D map of the real field + a Code 60 /
CHEQUERED banner).

## What it proves (and what it doesn't)

✅ **Proves the RaceSync → AC data path works end to end** inside Assetto Corsa: transport,
packet decode, and the coordinate transform — you see the 10-car field moving live.

❌ **Does not move collidable cars.** AC's Python app API can *read* car/physics state but
cannot *set* another car's world position. Phantoms you can actually race against require
the deeper Phase-1 spike — a server UDP plugin, a Custom Shaders Patch script, or a mod
(see [`specs/05-sim-injection-feasibility.md`](../../specs/05-sim-injection-feasibility.md)
§5.1–5.4). **This app is the right first validation to run when you have AC open**, before
investing in that harder path.

## Install

1. Copy the `RaceSyncPhantoms` folder into your AC apps directory:
   ```
   <Steam>/steamapps/common/assettocorsa/apps/python/RaceSyncPhantoms
   ```
2. Launch AC → **Settings → General → UI Modules** → enable **RaceSyncPhantoms**.
3. Start a session (any track/car — Practice is fine). Add the app from the right-edge app
   bar so its window is visible.

## Feed it from RaceSync

The app listens on **UDP `127.0.0.1:9013`** (matches `AssettoCorsaAdapter`'s default).
From the repo root, with AC running:

```bash
# Replay the generated 10-car field straight at AC over UDP:
python -m racesync.cli spike --nmea-dir examples/nmea --use-ac --ac-host 127.0.0.1 --ac-port 9013
```

You should see ~10 dots tracking the field, the phantom count update, and the banner switch
to **CODE 60** when a Code 60 packet arrives. (The `spike` command also prints a latency
report — note that offline-replay timestamps are logical, so for a *real* latency verdict
you feed live-captured timestamps; see specs/05 §5.4.)

If you only want to push positions without the spike report, any process that sends the
packets produced by `racesync.injection.assetto_corsa.encode_phantom_packet` /
`encode_global_packet` to that UDP port will drive the overlay.

## Packet format

Newline-terminated JSON, one car per packet:

```json
{"v":1,"seq":42,"car":"03","t":12.3,"x":124.5,"y":-88.2,"h":1.57,"spd":52.0,"q":1.0}
```

Global state:

```json
{"v":1,"global":{"code60":true,"chequered":false}}
```

The decode logic here mirrors `racesync.injection.assetto_corsa.decode_phantom_packet` and
`PhantomReceiver`, which are unit-tested in the main package — so the wire format is
verified even without AC.

## Notes

- Written for AC's bundled Python 3.3 (no f-strings / variable annotations).
- All socket and render work is wrapped in try/except and logs to AC's `py_log.txt`; a bad
  packet or transient error will never crash the session.
- Coordinates are RaceSync track-plane metres; the overlay auto-scales to the received
  field. A future version can load the surveyed SMSP centreline to draw the actual circuit
  outline (specs/02 TBC-1).
