"""Track frame: convert positions into the along-track representation RaceSync uses.

The track centreline is a closed polyline of (x, y) points in metres (track plane). It
provides the two conversions the Position Model needs (specs/04 §4.2):

* **map-matching** ``project(x, y)`` -> nearest point on the centreline, giving the
  along-track fraction ``s`` and the lateral offset. This snaps noisy GPS onto the track
  and yields the ordering key.
* **interpolation** ``point_at(s)`` -> (x, y, heading), used to place a car from a
  timing-only estimate between loops.

Geodetic input (lat/lon from a GPS source) is first projected to the track plane with an
equirectangular projection about a reference point (``model.geodetic_to_local``), then
map-matched here. Keeping a single along-track ``s`` as the lingua franca is what makes
fusing GPS and loop-timing tractable.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .model import geodetic_to_local


@dataclass(frozen=True)
class Projection:
    """Result of map-matching a point onto the centreline."""

    s: float          # fraction [0, 1) around the lap
    lateral: float    # signed metres from centreline (+left of travel direction)
    x: float          # snapped point on centreline
    y: float
    heading: float    # centreline direction at the snapped point (radians)
    distance: float   # absolute distance from the queried point to the centreline (m)


def _seg_closest(px, py, ax, ay, bx, by):
    """Closest point on segment AB to P; returns (t, qx, qy) with t in [0, 1]."""
    abx, aby = bx - ax, by - ay
    seg_len2 = abx * abx + aby * aby
    if seg_len2 == 0.0:
        return 0.0, ax, ay
    t = ((px - ax) * abx + (py - ay) * aby) / seg_len2
    t = max(0.0, min(1.0, t))
    return t, ax + t * abx, ay + t * aby


class TrackFrame:
    """A closed-loop centreline with along-track projection and interpolation.

    Parameters
    ----------
    centreline:
        Ordered (x, y) points in metres. Treated as a closed loop (last point joins
        back to the first). Must have at least 3 points.
    ref:
        Optional (lat, lon) reference for projecting geodetic inputs to this plane.
    name:
        Human label (e.g. "SMSP Gardner GP").
    """

    def __init__(self, centreline, ref=None, name="unnamed"):
        pts = [(float(x), float(y)) for x, y in centreline]
        if len(pts) < 3:
            raise ValueError("centreline needs at least 3 points")
        self.name = name
        self.ref = ref  # (lat, lon) or None
        self._pts = pts
        # Cumulative arc length at each vertex, plus total perimeter.
        cum = [0.0]
        for i in range(1, len(pts) + 1):
            ax, ay = pts[i - 1]
            bx, by = pts[i % len(pts)]
            cum.append(cum[-1] + math.dist((ax, ay), (bx, by)))
        self._cum = cum                 # len = n+1; last entry = perimeter
        self.length = cum[-1]           # metres per lap

    # -- construction helpers ---------------------------------------------- #

    @classmethod
    def from_geojson_line(cls, path, name=None):
        """Load a centreline from a GeoJSON LineString of [lon, lat] coordinates.

        The first coordinate is used as the projection reference. Useful once a surveyed
        SMSP centreline is available (specs/02 TBC-1).
        """
        data = json.loads(Path(path).read_text())
        coords = _extract_linestring(data)
        ref_lat, ref_lon = coords[0][1], coords[0][0]
        xy = [geodetic_to_local(lat, lon, ref_lat, ref_lon) for lon, lat in coords]
        # Drop a duplicated closing vertex if present (loop is implied).
        if len(xy) > 1 and math.dist(xy[0], xy[-1]) < 1e-6:
            xy = xy[:-1]
        return cls(xy, ref=(ref_lat, ref_lon), name=name or Path(path).stem)

    @property
    def points(self) -> list[tuple[float, float]]:
        """A copy of the centreline vertices (x, y) in metres."""
        return list(self._pts)

    # -- conversions -------------------------------------------------------- #

    def project(self, x: float, y: float) -> Projection:
        """Map-match a track-plane point to the nearest point on the centreline."""
        best = None
        n = len(self._pts)
        for i in range(n):
            ax, ay = self._pts[i]
            bx, by = self._pts[(i + 1) % n]
            t, qx, qy = _seg_closest(x, y, ax, ay, bx, by)
            d = math.dist((x, y), (qx, qy))
            if best is None or d < best[0]:
                seg_len = self._cum[i + 1] - self._cum[i]
                arc = self._cum[i] + t * seg_len
                heading = math.atan2(by - ay, bx - ax)
                # signed lateral offset: cross product of travel dir with (P - Q)
                cross = math.cos(heading) * (y - qy) - math.sin(heading) * (x - qx)
                best = (d, arc, qx, qy, heading, cross)
        d, arc, qx, qy, heading, lateral = best
        s = (arc / self.length) % 1.0
        return Projection(s=s, lateral=lateral, x=qx, y=qy, heading=heading, distance=d)

    def project_geodetic(self, lat: float, lon: float) -> Projection:
        if self.ref is None:
            raise ValueError("track has no geodetic reference; cannot project lat/lon")
        x, y = geodetic_to_local(lat, lon, self.ref[0], self.ref[1])
        return self.project(x, y)

    def point_at(self, s: float) -> tuple[float, float, float]:
        """Interpolate (x, y, heading) at along-track fraction ``s`` in [0, 1)."""
        s = s % 1.0
        target = s * self.length
        n = len(self._pts)
        # Find the segment whose cumulative span contains ``target``.
        for i in range(n):
            if self._cum[i] <= target <= self._cum[i + 1]:
                ax, ay = self._pts[i]
                bx, by = self._pts[(i + 1) % n]
                seg_len = self._cum[i + 1] - self._cum[i]
                t = 0.0 if seg_len == 0 else (target - self._cum[i]) / seg_len
                heading = math.atan2(by - ay, bx - ax)
                return ax + t * (bx - ax), ay + t * (by - ay), heading
        # Fallback (numerical edge at the seam): return the start vertex.
        ax, ay = self._pts[0]
        bx, by = self._pts[1]
        return ax, ay, math.atan2(by - ay, bx - ax)

    def forward_gap(self, s_from: float, s_to: float) -> float:
        """Forward fraction of a lap from ``s_from`` to ``s_to`` (handles wrap)."""
        return (s_to - s_from) % 1.0


def _extract_linestring(geojson):
    """Pull the first LineString coordinate list out of a GeoJSON document."""
    if geojson.get("type") == "LineString":
        return geojson["coordinates"]
    if geojson.get("type") == "Feature":
        return _extract_linestring(geojson["geometry"])
    if geojson.get("type") == "FeatureCollection":
        for feat in geojson["features"]:
            geom = feat.get("geometry", {})
            if geom.get("type") == "LineString":
                return geom["coordinates"]
    raise ValueError("no LineString found in GeoJSON")
