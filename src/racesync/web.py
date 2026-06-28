"""Live combined timing + track-map web view (Strategy-3 fallback & demo, specs/05, specs/08).

This is the guaranteed-deliverable surface: even if in-sim injection never lands, a browser
dashboard shows **both fields on the circuit map** plus a **combined real/virtual
leaderboard** and the race state (green / Code 60 / chequered). It doubles as the demo that
makes the pitch tangible and as the broadcast/operator overlay.

Design split (so it is testable without a browser or sockets):

* :func:`build_view_state` — a pure view-model builder (track + cars + standings + state).
* :func:`route` — pure request routing returning ``(status, content_type, body)``.
* :class:`LiveSession` — drives the pipeline (fusion + scoring + state engine) over a
  generated field, deterministically via :meth:`step_to` (tested) or in real time via
  :meth:`play` (a background thread).
* :func:`serve` / the CLI ``broadcast`` command — wire a real ``http.server`` to the above.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Callable, Optional

from .fusion import Fusion
from .model import RaceState, TimingEvent, TimingEventKind
from .scoring import CarClass, Entry, ScoringService
from .sources.base import RawFix
from .state_engine import RaceStateEngine
from .track import TrackFrame

# Race state -> a short banner label for the dashboard.
_BANNER = {
    RaceState.PRE_RACE: "PRE-RACE",
    RaceState.FORMATION: "FORMATION",
    RaceState.GREEN: "GREEN",
    RaceState.NEUTRALISED: "CODE 60",
    RaceState.CHEQUERED: "CHEQUERED",
}


def build_view_state(track: TrackFrame, cars: list[dict],
                     standings: dict[str, list[dict]], engine: RaceStateEngine,
                     now: float) -> dict:
    """Build the JSON view-model the dashboard polls.

    Args:
        track: Track frame whose centreline is drawn.
        cars: Per-car markers, each ``{id, x, y, klass, source, quality}``.
        standings: Mapping ``{"real": [...], "virtual": [...]}`` of standings rows.
        engine: Race-state engine (read for the banner and leader info).
        now: Current logical time in seconds.

    Returns:
        A JSON-serialisable dict with ``t``, ``state``, ``leader``, ``leader_lap``,
        ``track`` (centreline points), ``cars`` and ``standings``.
    """
    return {
        "t": round(now, 2),
        "state": engine.state.value,
        "banner": _BANNER[engine.state],
        "leader": engine.leader_car,
        "leader_lap": engine.leader_lap,
        "track": [[round(x, 1), round(y, 1)] for x, y in track.points],
        "cars": cars,
        "standings": standings,
    }


def route(path: str, state_provider: Callable[[], dict]) -> tuple[int, str, bytes]:
    """Route an HTTP path to a response, decoupled from any socket layer.

    Args:
        path: The request path (query string already stripped).
        state_provider: Callable returning the current view-model dict for ``/state``.

    Returns:
        A ``(status, content_type, body)`` tuple.
    """
    if path in ("/", "/index.html"):
        return 200, "text/html; charset=utf-8", INDEX_HTML.encode("utf-8")
    if path == "/state":
        body = json.dumps(state_provider()).encode("utf-8")
        return 200, "application/json", body
    return 404, "text/plain; charset=utf-8", b"not found"


class LiveSession:
    """Drives a generated hybrid field through fusion + scoring + state for the web view.

    A demo field (some real, some virtual cars) laps a track; the session advances it over
    logical time, synthesising lap-completed timing so scoring populates, and applies a
    scripted Code 60 window for liveliness. Thread-safe snapshots feed the server.

    Attributes:
        track: The circuit the field laps.
        fusion: Position fusion for the field.
        scoring: Scoring service producing the combined standings.
        engine: Shared race-state engine.
        duration: Loop length in seconds.
    """

    def __init__(self, track: Optional[TrackFrame] = None, n_real: int = 6,
                 n_virtual: int = 4, rate_hz: float = 10.0, duration: float = 120.0):
        from .simgen import default_field, make_smsp_track, simulate

        self.track = track or make_smsp_track()
        self.fusion = Fusion(self.track)
        self.scoring = ScoringService()
        self.engine = RaceStateEngine()
        self.duration = duration
        self._lock = threading.Lock()
        self._stop = threading.Event()

        # Build a mixed field: first n_real real (with divisions), rest virtual.
        n = n_real + n_virtual
        self._field = default_field(n)
        divisions = ["A", "B", "C", "D", "E"]
        for i, car in enumerate(self._field):
            if i < n_real:
                self.scoring.register(Entry(car.car_id, car.car_id, CarClass.REAL,
                                            f"Real {car.car_id}", divisions[i % 5]))
            else:
                self.scoring.register(Entry(car.car_id, car.car_id, CarClass.VIRTUAL,
                                            f"Sim {car.car_id}"))

        # Pre-compute the samples and group by ascending time.
        self._samples = simulate(self.track, self._field, rate_hz=rate_hz, duration_s=duration)
        self._idx = 0
        self._laps = {c.car_id: 0 for c in self._field}
        self._green = False
        self._code60_applied = {"on": False, "off": False}
        self.engine.arm(t=0.0)

    # -- deterministic stepping (testable) --------------------------------- #

    def step_to(self, t: float) -> None:
        """Advance the session to logical time ``t``, applying all samples up to it.

        Args:
            t: Logical time in seconds to advance to.
        """
        with self._lock:
            if not self._green and t >= 1.0:
                self.engine.go_green(t=1.0)
                self._green = True
            # Scripted Code 60 window for a lively demo.
            if not self._code60_applied["on"] and t >= self.duration * 0.4:
                if self.engine.state == RaceState.GREEN:
                    self.engine.set_code60(True, t=t)
                    self._code60_applied["on"] = True
            if not self._code60_applied["off"] and t >= self.duration * 0.55:
                if self.engine.state == RaceState.NEUTRALISED:
                    self.engine.set_code60(False, t=t)
                    self._code60_applied["off"] = True

            while self._idx < len(self._samples) and self._samples[self._idx].t <= t:
                s = self._samples[self._idx]
                est = self.fusion.on_fix(RawFix(car_id=s.car_id, t=s.t, lat=s.lat,
                                                lon=s.lon, speed=s.speed, heading=s.heading))
                self.scoring.on_position(est)
                lap = est.lap_distance.lap
                if lap > self._laps[s.car_id]:
                    self._laps[s.car_id] = lap
                    ev = TimingEvent(TimingEventKind.LAP_COMPLETED, t=s.t,
                                     car_id=s.car_id, lap=lap)
                    self.scoring.on_timing_event(ev)
                self._idx += 1

            # Leader = the real-class front-runner (display only).
            real = self.scoring.classify(CarClass.REAL, t).standings
            if real:
                self.engine.leader_car = real[0].score.entry.number
                self.engine.leader_lap = real[0].score.laps

    def snapshot(self, now: float) -> dict:
        """Return the current view-model for the dashboard.

        Args:
            now: Current logical time in seconds.

        Returns:
            The view-model dict from :func:`build_view_state`.
        """
        with self._lock:
            cars = []
            for car in self._field:
                est = self.fusion.latest(car.car_id)
                if est is None:
                    continue
                entry = next(e for e in self.scoring.entries() if e.car_id == car.car_id)
                cars.append({
                    "id": car.car_id, "x": round(est.x, 1), "y": round(est.y, 1),
                    "klass": entry.klass.value, "source": est.source.value,
                    "quality": round(est.quality, 2),
                })
            standings = {}
            for klass in (CarClass.REAL, CarClass.VIRTUAL):
                rows = []
                for st in self.scoring.classify(klass, now).standings:
                    e = st.score.entry
                    rows.append({
                        "pos": st.rank, "num": e.number, "driver": e.driver,
                        "div": e.division or "", "laps": st.score.laps,
                        "gap": "leader" if st.rank == 1 else f"-{st.gap_laps:g}L",
                        "source": st.score.source.value if st.score.source else "-",
                    })
                standings[klass.value] = rows
            return build_view_state(self.track, cars, standings, self.engine, now)

    # -- real-time play (background) --------------------------------------- #

    def play(self, speed: float = 1.0) -> None:  # pragma: no cover - timing loop
        """Replay the field in real time on a background thread, looping forever.

        Args:
            speed: Playback speed multiplier (1.0 = real time).
        """
        start = time.monotonic()
        while not self._stop.is_set():
            now = (time.monotonic() - start) * speed
            if now >= self.duration:
                self._reset()
                start = time.monotonic()
                continue
            self.step_to(now)
            time.sleep(0.05)

    def start(self, speed: float = 1.0) -> threading.Thread:  # pragma: no cover
        """Start :meth:`play` on a daemon thread and return it."""
        th = threading.Thread(target=self.play, args=(speed,), daemon=True)
        th.start()
        return th

    def stop(self) -> None:  # pragma: no cover
        """Signal the play loop to stop."""
        self._stop.set()

    def _reset(self) -> None:  # pragma: no cover - loop bookkeeping
        with self._lock:
            self.fusion = Fusion(self.track)
            self._idx = 0
            self._laps = {c.car_id: 0 for c in self._field}


def serve(session: "LiveSession", host: str = "127.0.0.1",
          port: int = 8013) -> None:  # pragma: no cover - live server
    """Serve the dashboard for a session, playing it in real time until interrupted.

    Args:
        session: The live session to render.
        host: Interface to bind.
        port: TCP port to listen on.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    session.start()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            status, ctype, body = route(self.path.split("?")[0],
                                        lambda: session.snapshot(session._last_now()))
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # silence default logging
            pass

    # Track a wall clock for snapshots.
    start = time.monotonic()
    session._last_now = lambda: min((time.monotonic() - start), session.duration)
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"RaceSync broadcast view: http://{host}:{port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        session.stop()


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>RaceSync — live</title>
<style>
  :root{--red:#e2231a;--cyan:#2fb8ff;--bg:#0d1014;--panel:#161b22;--muted:#7c8a98;}
  *{box-sizing:border-box;} body{margin:0;background:var(--bg);color:#eef2f6;
    font-family:Segoe UI,Helvetica,Arial,sans-serif;}
  header{display:flex;align-items:center;gap:16px;padding:10px 16px;
    border-bottom:3px solid var(--red);}
  .brand{font-size:22px;font-weight:800;} .brand .s{color:var(--cyan);}
  #banner{font-weight:800;padding:4px 12px;border-radius:4px;background:#2b6;color:#001;}
  #banner.code60{background:#ffce3a;} #banner.chequered{background:#fff;color:#000;}
  #banner.prerace,#banner.formation{background:#445;color:#fff;}
  .wrap{display:grid;grid-template-columns:2fr 1fr;gap:14px;padding:14px;}
  canvas{width:100%;background:#0a0d11;border:1px solid #20262e;border-radius:8px;}
  .board{background:var(--panel);border:1px solid #20262e;border-radius:8px;padding:10px;}
  h3{margin:4px 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:.5px;}
  h3.real{color:var(--red);} h3.virtual{color:var(--cyan);}
  table{width:100%;border-collapse:collapse;font-size:13px;}
  td,th{padding:3px 6px;text-align:left;border-bottom:1px solid #20262e;}
  th{color:var(--muted);font-weight:600;} .muted{color:var(--muted);font-size:12px;}
</style></head><body>
<header>
  <div class="brand">Race<span class="s">Sync</span></div>
  <div id="banner">—</div>
  <div class="muted">Leader: <span id="leader">—</span></div>
  <div class="muted" style="margin-left:auto" id="clock">t=0s</div>
</header>
<div class="wrap">
  <canvas id="map" width="900" height="560"></canvas>
  <div>
    <div class="board"><h3 class="real">Real class</h3><table id="real"></table></div>
    <div class="board" style="margin-top:12px"><h3 class="virtual">Virtual class</h3>
      <table id="virtual"></table></div>
  </div>
</div>
<script>
const cv = document.getElementById('map'), ctx = cv.getContext('2d');
function bounds(pts){let xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);
  let x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
  let w=x1-x0||1,h=y1-y0||1,pad=0.08*Math.max(w,h);
  return [x0-pad,y0-pad,w+2*pad,h+2*pad];}
function draw(s){
  const pts=s.track; if(!pts.length)return;
  const [bx,by,bw,bh]=bounds(pts);
  const sc=Math.min(cv.width/bw, cv.height/bh);
  const ox=(cv.width-bw*sc)/2, oy=(cv.height-bh*sc)/2;
  const X=x=>ox+(x-bx)*sc, Y=y=>oy+(bh-(y-by))*sc;
  ctx.clearRect(0,0,cv.width,cv.height);
  ctx.strokeStyle='#3a7'; ctx.lineWidth=2; ctx.beginPath();
  pts.forEach((p,i)=>{const x=X(p[0]),y=Y(p[1]); i?ctx.lineTo(x,y):ctx.moveTo(x,y);});
  ctx.closePath(); ctx.stroke();
  for(const c of s.cars){
    ctx.beginPath(); ctx.arc(X(c.x),Y(c.y),6,0,7);
    ctx.fillStyle = c.klass==='real' ? '#e2231a' : '#2fb8ff';
    ctx.globalAlpha = c.source==='dead_reckoned'?0.45:1; ctx.fill(); ctx.globalAlpha=1;
    ctx.fillStyle='#cdd6df'; ctx.font='11px monospace'; ctx.fillText(c.id, X(c.x)+8, Y(c.y)+3);
  }
}
function fillTable(id, rows){
  let h='<tr><th>P</th><th>No</th><th>Driver</th><th>Div</th><th>Laps</th><th>Gap</th></tr>';
  for(const r of rows){h+=`<tr><td>${r.pos}</td><td>${r.num}</td><td>${r.driver}</td>`+
    `<td>${r.div}</td><td>${r.laps}</td><td>${r.gap}</td></tr>`;}
  document.getElementById(id).innerHTML=h;
}
async function tick(){
  try{
    const s=await (await fetch('/state')).json();
    const b=document.getElementById('banner');
    b.textContent=s.banner; b.className=s.state;
    document.getElementById('leader').textContent=(s.leader||'—')+' (lap '+s.leader_lap+')';
    document.getElementById('clock').textContent='t='+Math.round(s.t)+'s';
    draw(s); fillTable('real', s.standings.real||[]); fillTable('virtual', s.standings.virtual||[]);
  }catch(e){}
}
setInterval(tick, 250); tick();
</script>
</body></html>
"""
