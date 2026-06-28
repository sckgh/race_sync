"""Standalone phantom visualizer — see the cars on the track without a simulator.

Renders the track centreline plus each car's position to:

* an **SVG** snapshot (``track_svg``) — open in any browser, or
* an **ASCII** map (``track_ascii``) — for the terminal / CI logs.

This is the cheap, dependency-free way to confirm that positions land where they should
(map-matching, coordinate transforms, ordering) before tackling true sim injection. It
consumes anything position-like: ``PositionEstimate`` (from fusion) or ``PhantomState``
(from the injection path) — both expose ``car_id``, ``x``, ``y``.
"""

from __future__ import annotations

from typing import Iterable

from .track import TrackFrame


def _bounds(points: Iterable[tuple[float, float]], pad_frac: float = 0.08):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w = maxx - minx or 1.0
    h = maxy - miny or 1.0
    pad = pad_frac * max(w, h)
    return minx - pad, miny - pad, w + 2 * pad, h + 2 * pad


def track_svg(track: TrackFrame, cars: Iterable, width: int = 720,
              title: str = "", banner: str = "") -> str:
    """Render the track + car markers to an SVG string.

    ``cars`` is any iterable of objects with ``car_id``, ``x``, ``y`` (and optional
    ``source``/``quality`` for colouring).
    """
    pts = track.points
    bx, by, bw, bh = _bounds(pts)
    scale = width / bw
    height = int(bh * scale) + 40

    def sx(x: float) -> float:
        return (x - bx) * scale

    def sy(y: float) -> float:
        # SVG y grows downward; flip so north is up.
        return (bh - (y - by)) * scale + 30

    poly = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in pts)
    first = pts[0]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="monospace">',
        f'<rect width="{width}" height="{height}" fill="#0b0f14"/>',
        f'<text x="10" y="20" fill="#cfe" font-size="14">{_esc(title)}</text>',
        f'<text x="{width - 10}" y="20" fill="#fd6" font-size="14" '
        f'text-anchor="end">{_esc(banner)}</text>',
        f'<polygon points="{poly}" fill="none" stroke="#2b6" stroke-width="2"/>',
        # start/finish marker
        f'<circle cx="{sx(first[0]):.1f}" cy="{sy(first[1]):.1f}" r="4" fill="#fff"/>',
    ]
    palette = {"gps": "#6cf", "fused": "#9f9", "timing_interp": "#fc6",
               "dead_reckoned": "#f86"}
    for c in cars:
        colour = palette.get(getattr(getattr(c, "source", None), "value", None), "#6cf")
        cx, cy = sx(c.x), sy(c.y)
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" fill="{colour}" '
                     f'stroke="#000" stroke-width="1"/>')
        parts.append(f'<text x="{cx + 8:.1f}" y="{cy + 4:.1f}" fill="#eee" '
                     f'font-size="11">{_esc(str(c.car_id))}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def track_ascii(track: TrackFrame, cars: Iterable, width: int = 70, height: int = 24) -> str:
    """Render the track + cars as an ASCII grid (track = '.', cars = their id's 1st char)."""
    pts = track.points
    bx, by, bw, bh = _bounds(pts)
    grid = [[" "] * width for _ in range(height)]

    def cell(x: float, y: float) -> tuple[int, int]:
        gx = int((x - bx) / bw * (width - 1))
        gy = int((bh - (y - by)) / bh * (height - 1))
        return max(0, min(width - 1, gx)), max(0, min(height - 1, gy))

    # Draw the centreline by sampling along s for a continuous outline.
    n = max(len(pts) * 4, 200)
    for i in range(n):
        x, y, _ = track.point_at(i / n)
        gx, gy = cell(x, y)
        grid[gy][gx] = "."
    for c in cars:
        gx, gy = cell(c.x, c.y)
        grid[gy][gx] = str(c.car_id)[0]
    return "\n".join("".join(row) for row in grid)


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
