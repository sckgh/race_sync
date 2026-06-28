import math

import pytest

from racesync.track import TrackFrame


def square_track(side=100.0):
    """A 4-vertex square loop, perimeter = 4*side, centred at origin."""
    h = side / 2
    return TrackFrame([(-h, -h), (h, -h), (h, h), (-h, h)], name="square")


def test_length_is_perimeter():
    t = square_track(100.0)
    assert t.length == pytest.approx(400.0)


def test_project_on_centreline_has_zero_distance():
    t = square_track(100.0)
    # Midpoint of the bottom edge lies on the centreline.
    p = t.project(0.0, -50.0)
    assert p.distance == pytest.approx(0.0, abs=1e-9)
    # s should be 1/8 of the way around (half of the first of four equal edges).
    assert p.s == pytest.approx(1 / 8, abs=1e-6)


def test_project_lateral_offset_sign():
    t = square_track(100.0)
    # On the bottom edge travel direction is +x; a point "inside" (north) the loop is to
    # the left of travel, so lateral should be positive.
    inside = t.project(0.0, -40.0)
    outside = t.project(0.0, -60.0)
    assert inside.lateral > 0
    assert outside.lateral < 0
    assert inside.distance == pytest.approx(10.0)
    assert outside.distance == pytest.approx(10.0)


def test_point_at_round_trips_with_project():
    t = square_track(100.0)
    for s in (0.0, 0.1, 0.25, 0.5, 0.73, 0.99):
        x, y, _ = t.point_at(s)
        back = t.project(x, y)
        assert back.s == pytest.approx(s, abs=1e-6)


def test_forward_gap_wraps():
    t = square_track()
    assert t.forward_gap(0.9, 0.1) == pytest.approx(0.2)
    assert t.forward_gap(0.1, 0.9) == pytest.approx(0.8)


def test_needs_three_points():
    with pytest.raises(ValueError):
        TrackFrame([(0, 0), (1, 1)])


def test_geojson_loading(tmp_path):
    import json

    # A tiny square in lon/lat near SMSP; just check it builds and projects.
    coords = [[150.870, -33.800], [150.871, -33.800],
              [150.871, -33.801], [150.870, -33.801], [150.870, -33.800]]
    gj = {"type": "LineString", "coordinates": coords}
    p = tmp_path / "track.geojson"
    p.write_text(json.dumps(gj))
    t = TrackFrame.from_geojson_line(p)
    assert t.ref is not None
    assert t.length > 0
    # A geodetic point near the first vertex should map-match close to s=0.
    proj = t.project_geodetic(-33.8001, 150.8701)
    assert 0.0 <= proj.s < 1.0
