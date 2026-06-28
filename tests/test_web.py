import json

import pytest

from racesync.scoring import CarClass
from racesync.state_engine import RaceStateEngine
from racesync.track import TrackFrame
from racesync.web import INDEX_HTML, LiveSession, build_view_state, route


def square():
    return TrackFrame([(-200, -200), (200, -200), (200, 200), (-200, 200)])


# -- pure view-model + routing --------------------------------------------- #

def test_build_view_state_shape():
    engine = RaceStateEngine()
    engine.arm(t=0.0)
    engine.go_green(t=1.0)
    engine.leader_car = "1"
    engine.leader_lap = 3
    cars = [{"id": "1", "x": 0.0, "y": -200.0, "klass": "real", "source": "gps", "quality": 1.0}]
    standings = {"real": [{"pos": 1, "num": "1", "driver": "A", "div": "B",
                           "laps": 3, "gap": "leader", "source": "gps"}], "virtual": []}
    vs = build_view_state(square(), cars, standings, engine, now=42.0)
    assert vs["state"] == "green" and vs["banner"] == "GREEN"
    assert vs["leader"] == "1" and vs["leader_lap"] == 3
    assert vs["t"] == 42.0
    assert len(vs["track"]) == 4
    assert vs["cars"][0]["id"] == "1"
    assert vs["standings"]["real"][0]["pos"] == 1


def test_route_serves_html_json_and_404():
    provider = lambda: {"hello": "world"}
    s, ctype, body = route("/", provider)
    assert s == 200 and "text/html" in ctype and b"<canvas" in body
    s, ctype, body = route("/state", provider)
    assert s == 200 and ctype == "application/json"
    assert json.loads(body) == {"hello": "world"}
    s, ctype, body = route("/nope", provider)
    assert s == 404


def test_index_html_is_self_contained():
    assert "<!DOCTYPE html>" in INDEX_HTML
    assert "/state" in INDEX_HTML            # the page polls the state endpoint
    assert "RaceSync" in INDEX_HTML


# -- live session (deterministic stepping) --------------------------------- #

def test_live_session_populates_both_classes():
    sess = LiveSession(n_real=4, n_virtual=3, rate_hz=10.0, duration=60.0)
    sess.step_to(10.0)
    snap = sess.snapshot(10.0)
    # Both classes have entries; cars are on the map.
    assert len(snap["standings"]["real"]) == 4
    assert len(snap["standings"]["virtual"]) == 3
    assert len(snap["cars"]) == 7
    # Race went green by t>=1.
    assert snap["state"] in ("green", "neutralised")
    assert snap["leader"] is not None


def test_live_session_cars_map_matched_onto_track():
    sess = LiveSession(n_real=3, n_virtual=2, duration=60.0)
    sess.step_to(5.0)
    for c in sess.snapshot(5.0)["cars"]:
        proj = sess.track.project(c["x"], c["y"])
        assert proj.distance < 1.0          # on the centreline


def test_live_session_scripted_code60_window():
    sess = LiveSession(n_real=3, n_virtual=2, duration=100.0)
    sess.step_to(30.0)
    assert sess.snapshot(30.0)["state"] == "green"
    sess.step_to(45.0)                       # past the 0.4*duration Code 60 trigger
    assert sess.snapshot(45.0)["state"] == "neutralised"
    sess.step_to(60.0)                       # past the 0.55*duration restart
    assert sess.snapshot(60.0)["state"] == "green"


def test_live_session_classes_split_real_virtual():
    sess = LiveSession(n_real=6, n_virtual=4, duration=60.0)
    reals = [e for e in sess.scoring.entries() if e.klass == CarClass.REAL]
    virts = [e for e in sess.scoring.entries() if e.klass == CarClass.VIRTUAL]
    assert len(reals) == 6 and len(virts) == 4
