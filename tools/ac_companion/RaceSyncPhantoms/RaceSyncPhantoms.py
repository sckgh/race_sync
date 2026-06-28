# RaceSync Phantoms - Assetto Corsa companion app
#
# Receives phantom-car packets from RaceSync over UDP and visualises them as an in-sim
# overlay (a 2D scatter map + a Code 60 / CHEQUERED banner). This is the SIM-SIDE endpoint
# of the injection wire path documented in specs/05 and specs/12.
#
# IMPORTANT - what this does and does NOT do:
#   * It DOES prove the RaceSync -> AC data path end to end (transport, decode, the
#     coordinate transform) and shows the real field moving live, inside AC.
#   * It does NOT move collidable AI/opponent cars. The Assetto Corsa Python app API can
#     READ car/physics state but cannot SET another car's world position. True in-world
#     injection (phantoms you can race against) needs the deeper Phase-1 spike: a server
#     UDP plugin, a Custom Shaders Patch script, or a mod (specs/05 §5.1-5.4). This app is
#     the right FIRST validation to run when AC is available.
#
# Install: copy the parent "RaceSyncPhantoms" folder into
#   <Assetto Corsa>/apps/python/RaceSyncPhantoms
# then enable "RaceSyncPhantoms" in AC > Settings > General > UI Modules.
#
# Written for AC's bundled Python 3.3 (no f-strings, no variable annotations).

import socket
import json
import traceback

try:
    import ac
    import acsys
except ImportError:
    ac = None  # allows linting/importing outside AC

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 9013          # must match AssettoCorsaAdapter(host, port) in RaceSync

# Module state
app_window = None
label_status = None
sock = None
phantoms = {}               # car_id -> dict(x, y, h, spd, q, seq)
last_seq = {}               # car_id -> int
global_state = {"code60": False, "chequered": False}

MAP_X, MAP_Y = 10, 70       # overlay origin within the app window (px)
MAP_W, MAP_H = 300, 170


def _init_socket():
    global sock
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((LISTEN_HOST, LISTEN_PORT))
        sock.setblocking(False)
        ac.log("RaceSyncPhantoms: listening on {0}:{1}".format(LISTEN_HOST, LISTEN_PORT))
    except Exception:
        ac.log("RaceSyncPhantoms: socket error\n" + traceback.format_exc())
        sock = None


def _handle_packet(data):
    try:
        obj = json.loads(data.decode("utf-8").strip())
    except Exception:
        return
    if "global" in obj and isinstance(obj["global"], dict):
        global_state["code60"] = bool(obj["global"].get("code60", False))
        global_state["chequered"] = bool(obj["global"].get("chequered", False))
        return
    if "car" not in obj:
        return
    car = str(obj["car"])
    seq = int(obj.get("seq", 0))
    if car in last_seq and seq < last_seq[car]:
        return                                  # stale / out of order on UDP
    last_seq[car] = seq
    phantoms[car] = {
        "x": float(obj.get("x", 0.0)),
        "y": float(obj.get("y", 0.0)),
        "h": float(obj.get("h", 0.0)),
        "spd": obj.get("spd"),
        "q": float(obj.get("q", 1.0)),
    }


def _drain():
    if sock is None:
        return
    for _ in range(2000):                       # bound work per frame
        try:
            data, _addr = sock.recvfrom(2048)
        except (BlockingIOError, socket.error):
            break
        except Exception:
            break
        _handle_packet(data)


def _banner_text():
    if global_state["chequered"]:
        return "CHEQUERED"
    if global_state["code60"]:
        return "*** CODE 60 ***"
    return "GREEN"


def _bounds():
    if not phantoms:
        return 0.0, 0.0, 1.0, 1.0
    xs = [p["x"] for p in phantoms.values()]
    ys = [p["y"] for p in phantoms.values()]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w = (maxx - minx) or 1.0
    h = (maxy - miny) or 1.0
    pad = 0.08 * max(w, h)
    return minx - pad, miny - pad, w + 2 * pad, h + 2 * pad


def onRender(deltaT):
    if ac is None:
        return
    try:
        bx, by, bw, bh = _bounds()
        for car, p in phantoms.items():
            sx = MAP_X + (p["x"] - bx) / bw * MAP_W
            sy = MAP_Y + (bh - (p["y"] - by)) / bh * MAP_H   # flip so north is up
            q = p["q"]
            # colour by data quality: green good -> red poor
            ac.glColor4f(1.0 - q, 0.3 + 0.6 * q, 0.3, 1.0)
            ac.glQuad(sx - 3, sy - 3, 6, 6)
        if global_state["code60"]:
            ac.glColor4f(1.0, 0.8, 0.0, 1.0)
            ac.glQuad(MAP_X, MAP_Y - 14, MAP_W, 4)
    except Exception:
        ac.log("RaceSyncPhantoms render error\n" + traceback.format_exc())


def acMain(version):
    global app_window, label_status
    app_window = ac.newApp("RaceSync Phantoms")
    ac.setSize(app_window, MAP_W + 20, MAP_H + 90)
    label_status = ac.addLabel(app_window, "RaceSync: waiting for data...")
    ac.setPosition(label_status, 10, 30)
    ac.addRenderCallback(app_window, onRender)
    _init_socket()
    return "RaceSyncPhantoms"


def acUpdate(deltaT):
    if ac is None:
        return
    _drain()
    ac.setText(label_status,
               "phantoms: {0}   state: {1}".format(len(phantoms), _banner_text()))
