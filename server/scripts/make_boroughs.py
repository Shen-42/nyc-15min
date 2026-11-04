"""Make geo/boroughs.json, the land of the five boroughs (card 15).

The source is the NYC Department of City Planning's borough boundaries, cut
to the shoreline, as published by Code for Germany's Click That 'Hood:
    https://github.com/codeforgermany/click_that_hood/blob/main/public/data/new-york-city-boroughs.geojson
Save that file anywhere and run, from the server folder:
    python scripts/make_boroughs.py path/to/new-york-city-boroughs.geojson

It writes geo/boroughs.json and the site's copy, client/src/data/boroughs.json.
Both are committed: borough lines and shorelines barely change, so
this only needs running again to change the detail. It uses the standard
library only.

Output: {"meta": {...}, "boroughs": {"Manhattan": [ring, ...], ...}}, where
each ring is a polygon's outline as [lat, lng] points (holes left out).
"""

import json
import math
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
# The server's copy, and the site's.
OUTPUT_FILES = [SERVER_DIR / "geo" / "boroughs.json", SERVER_DIR.parent / "client" / "src" / "data" / "boroughs.json"]

# Outlines are straightened to within this many meters: about the width of
# a sidewalk, and a quarter of the points of the full detail.
SIMPLIFY_M = 5
# Islands smaller than this (rocks, piers) are left out.
MIN_AREA_M2 = 5_000

NAMES = {"Bronx": "Bronx", "Brooklyn": "Brooklyn", "Manhattan": "Manhattan", "Queens": "Queens", "Staten Island": "Staten Island"}

# Meters per degree around the middle of the city.
LAT0 = 40.7
M_PER_DEG_LAT = 110_540
M_PER_DEG_LNG = 111_320 * math.cos(math.radians(LAT0))


def to_m(lng, lat):
    return (lng * M_PER_DEG_LNG, lat * M_PER_DEG_LAT)


def area_m2(points):
    """Shoelace formula, for points in meters."""
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]))) / 2


def simplify(points, tolerance):
    """Douglas-Peucker: keep the points that bend the line more than `tolerance`."""
    if len(points) < 3:
        return list(range(len(points)))
    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = points[a], points[b]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        far, far_i = -1.0, None
        for i in range(a + 1, b):
            x, y = points[i]
            d = abs(dy * (x - x1) - dx * (y - y1)) / length if length else math.hypot(x - x1, y - y1)
            if d > far:
                far, far_i = d, i
        if far_i is not None and far > tolerance:
            keep.add(far_i)
            stack += [(a, far_i), (far_i, b)]
    return sorted(keep)


def crosses_itself(points):
    """Does a closed ring cross itself? Checks every pair of non-adjacent edges."""
    n = len(points)
    edges = [(points[i], points[(i + 1) % n]) for i in range(n)]
    boxes = [(min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])) for a, b in edges]

    def side(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 0) - (v < 0)

    order = sorted(range(n), key=lambda i: boxes[i][0])  # sweep from west to east
    active = []
    for i in order:
        x0, x1, y0, y1 = boxes[i]
        active = [j for j in active if boxes[j][1] >= x0]
        for j in active:
            if abs(i - j) in (1, n - 1):
                continue  # neighbors share a corner
            bx0, bx1, by0, by1 = boxes[j]
            if by1 < y0 or by0 > y1:
                continue
            (p1, p2), (p3, p4) = edges[i], edges[j]
            if side(p1, p2, p3) * side(p1, p2, p4) < 0 and side(p3, p4, p1) * side(p3, p4, p2) < 0:
                return True
        active.append(i)
    return False


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    source = json.loads(Path(sys.argv[1]).read_text())
    boroughs = {}
    for feature in source["features"]:
        name = NAMES[feature["properties"]["name"]]
        geom = feature["geometry"]
        polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        rings = []
        for polygon in polygons:
            outer = polygon[0]  # [lng, lat] points; holes are left out
            points = [to_m(lng, lat) for lng, lat in outer]
            if area_m2(points) < MIN_AREA_M2:
                continue
            # Simplifying can make a narrow inlet cross itself. Ask for less
            # simplifying until it doesn't: such a ring breaks shape joins.
            tolerance = SIMPLIFY_M
            kept = simplify(points, tolerance)
            while crosses_itself([points[i] for i in kept]) and tolerance > 0.1:
                tolerance /= 2
                kept = simplify(points, tolerance)
            if tolerance < SIMPLIFY_M:
                print(f"{name}: one ring kept to {tolerance:g} m so it doesn't cross itself")
            if len(kept) >= 4:
                rings.append([[round(outer[i][1], 6), round(outer[i][0], 6)] for i in kept])
        rings.sort(key=lambda ring: -area_m2([to_m(lng, lat) for lat, lng in ring]))  # biggest first
        boroughs[name] = rings

    text = json.dumps({
        "meta": {
            "source": "NYC Department of City Planning borough boundaries (clipped to shoreline), via Click That 'Hood",
            "simplify_m": SIMPLIFY_M,
            "min_area_m2": MIN_AREA_M2,
            "format": "boroughs: {name: [ring of [lat, lng], ...]}, outer rings only, biggest first",
        },
        "boroughs": dict(sorted(boroughs.items())),
    }, separators=(",", ":"))
    for out in OUTPUT_FILES:
        out.parent.mkdir(exist_ok=True)
        out.write_text(text)
        print(f"Saved {out} ({out.stat().st_size / 1000:.0f} KB)")
    for name, rings in sorted(boroughs.items()):
        print(f"{name:14} {len(rings):3} pieces of land, {sum(len(r) for r in rings):6,} points")


if __name__ == "__main__":
    main()
