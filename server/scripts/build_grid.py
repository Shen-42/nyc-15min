"""Score every 100 m of New York City, and find the gaps (cards 12 and 15).

Run from the server folder after the other build scripts:
    python scripts/build_grid.py

For each square of a 100 m grid on land, it runs the same 15-minute walk as
the site (walking, any time) and saves each category's score. Then, in each
borough and for each category, it finds the squares with no such place in
reach ("gaps") and the one square where a new place would put the most gap
squares within 15 minutes.

It writes one file per borough, data/grid-<borough>.json, used by the
server to rank a spot and by the site for the score map and gap finder.
About 70,000 squares in all; a few minutes on GitHub Actions. It needs
NumPy and the server's own graph.py, amenities.py, and scoring.py.
"""

import json
import math
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))
from amenities import PlaceIndex, load_amenities  # noqa: E402
from graph import WALK_SPEED_M_PER_MIN, WalkGraph, distance_m  # noqa: E402
from scoring import CATEGORY_SETTINGS, score_walk  # noqa: E402

DATA = SERVER_DIR / "data"
BOROUGHS_FILE = SERVER_DIR / "geo" / "boroughs.json"

CELL_M = 100
MINUTES = 15
# The same limits as the site (main.py): a square whose center is farther than
# this from any path (a rail yard, the middle of a pier) is left out.
MAX_START_GAP_M = 150
# How far from a spot to look for a named intersection to describe it.
MAX_LABEL_M = 300
# Failing that, how far to look for a named place instead.
MAX_PLACE_LABEL_M = 600
# A square is "in a park" when most of it lies inside a park outline from
# OpenStreetMap (data/parks.json, saved by build_amenities.py): at least
# PARK_SHARE of PARK_SAMPLES x PARK_SAMPLES points spread over the square.
# Nobody lives in a park, so park squares are left out of the gaps, the best
# spots, the rank, and the heat map.
PARK_SAMPLES = 3
PARK_SHARE = 0.5
# Islands where nobody lives, left out of the grid like parks: the gaps and
# best spots are about where people live. A point on each; the whole piece of
# land around it is left out. (Clicks there still work.) Islands with no
# paths at all, like the marshes in Jamaica Bay, drop out on their own.
NOT_LIVED_ON = {
    "Randalls and Wards Islands": (40.7929, -73.9255),
    "Governors Island": (40.6889, -74.0168),
    "Liberty Island": (40.6892, -74.0445),
    "Ellis Island": (40.6990, -74.0396),
    "Rikers Island": (40.7934, -73.8845),
    "Hart Island": (40.8527, -73.7710),
    "North Brother Island": (40.8008, -73.8990),
    "South Brother Island": (40.7962, -73.8977),
}

# Outlines sent to the site are rounded to 5 decimals, about 1 m.
OUTLINE_DECIMALS = 5

CATEGORIES = list(CATEGORY_SETTINGS)
# In each square's flags: bit k is set when category k has nothing in reach.
PARK_BIT = 1 << len(CATEGORIES)

# The grid's spacing. Columns use the longitude scale at this latitude, the
# middle of the city, so squares are 100 m wide to within 1% everywhere.
LAT0 = 40.78
M_PER_DEG_LAT = 110_540
M_PER_DEG_LNG = 111_320 * math.cos(math.radians(LAT0))
STEP_LAT = CELL_M / M_PER_DEG_LAT
STEP_LNG = CELL_M / M_PER_DEG_LNG


def slug(borough):
    """ "Staten Island" -> "staten-island", for file names."""
    return borough.lower().replace(" ", "-")


def inside(rings, lats, lngs):
    """Which points of a lattice (every lat in `lats` with every lng in
    `lngs`, both sorted) are inside the rings, by the even-odd rule: a point
    is inside if a line from it crosses the outlines an odd number of times.
    One row at a time: find where the edges cross that row's latitude, sort
    the crossings, and count how many lie west of each point. Returns a
    boolean array of shape (len(lats), len(lngs)).

    Overlapping rings cancel out, like holes, so pass one shape at a time
    (an outline and its holes) and combine shapes with `|`.
    """
    out = np.zeros((len(lats), len(lngs)), dtype=bool)
    edges = []
    for ring in rings:
        r = np.asarray(ring, dtype=np.float64)
        edges.append(np.column_stack([r, np.roll(r, -1, axis=0)]))  # lat1, lng1, lat2, lng2
    if not edges:
        return out
    e = np.concatenate(edges)
    e = e[e[:, 0] != e[:, 2]]  # flat edges never cross a row
    lo, hi = np.minimum(e[:, 0], e[:, 2]), np.maximum(e[:, 0], e[:, 2])
    first, last = np.searchsorted(lats, lo.min()), np.searchsorted(lats, hi.max(), side="right")
    for row in range(first, last):
        lat = lats[row]
        crossing = (lo <= lat) & (lat < hi)
        if not crossing.any():
            continue
        c = e[crossing]
        xs = np.sort(c[:, 1] + (lat - c[:, 0]) / (c[:, 2] - c[:, 0]) * (c[:, 3] - c[:, 1]))
        out[row] = np.searchsorted(xs, lngs) % 2 == 1
    return out


def load_boroughs():
    return json.loads(BOROUGHS_FILE.read_text())["boroughs"]


def lived_on(rings):
    """The pieces of land that hold none of the NOT_LIVED_ON points."""
    keep = []
    for ring in rings:
        hits = [name for name, (lat, lng) in NOT_LIVED_ON.items() if inside([ring], np.array([lat]), np.array([lng]))[0, 0]]
        if hits:
            print(f"  left out: {', '.join(hits)}")
        else:
            keep.append(ring)
    return keep


def load_water():
    """Lakes and ponds as lists of rings in [lat, lng]: [outer, hole, hole, ...]."""
    shapes = []
    for item in json.loads((DATA / "water.json").read_text()):
        geom = item["geometry"]
        parts = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for rings in parts:
            shapes.append([[[lat, lng] for lng, lat in ring] for ring in rings])
    return shapes


def load_parks():
    """Park outlines as lists of outer rings in [lat, lng] (one list per park)."""
    parks_file = DATA / "parks.json"
    if not parks_file.exists():
        sys.exit("No park outlines yet. Run python scripts/build_amenities.py first.")
    return [park["rings"] for park in json.loads(parks_file.read_text()) if park["rings"]]


def shapes_inside(shapes, lats, lngs):
    """inside() for many separate shapes (parks, lakes), each checked only
    over the part of the lattice its bounding box covers."""
    out = np.zeros((len(lats), len(lngs)), dtype=bool)
    for rings in shapes:
        pts = np.concatenate([np.asarray(r) for r in rings])
        r0, r1 = np.searchsorted(lats, pts[:, 0].min()), np.searchsorted(lats, pts[:, 0].max(), side="right")
        c0, c1 = np.searchsorted(lngs, pts[:, 1].min()), np.searchsorted(lngs, pts[:, 1].max(), side="right")
        if r0 < r1 and c0 < c1:
            out[r0:r1, c0:c1] |= inside(rings, lats[r0:r1], lngs[c0:c1])
    return out


def lattice(boroughs):
    """The grid's origin and the latitudes and longitudes of its square centers."""
    pts = np.array([p for rings in boroughs.values() for ring in rings for p in ring])
    lat0, lng0 = pts[:, 0].min(), pts[:, 1].min()
    rows = int((pts[:, 0].max() - lat0) / STEP_LAT) + 1
    cols = int((pts[:, 1].max() - lng0) / STEP_LNG) + 1
    lats = lat0 + (np.arange(rows) + 0.5) * STEP_LAT
    lngs = lng0 + (np.arange(cols) + 0.5) * STEP_LNG
    return (lat0, lng0), lats, lngs


def park_share(parks, lats, lngs):
    """The share of PARK_SAMPLES x PARK_SAMPLES points in each square that lie in a park."""
    n = PARK_SAMPLES
    offsets = (np.arange(n) + 0.5) / n - 0.5  # -1/3, 0, 1/3 of a square
    fine_lats = (lats[:, None] + offsets * STEP_LAT).ravel()
    fine_lngs = (lngs[:, None] + offsets * STEP_LNG).ravel()
    fine = shapes_inside(parks, fine_lats, fine_lngs)
    return fine.reshape(len(lats), n, len(lngs), n).mean(axis=(1, 3))


def named_corners(graph):
    """[(lat, lng, "Street & Street")] to describe a spot by its cross streets.
    The curb ramp data names both streets at almost every corner.
    OpenStreetMap's own names, from the graph, fill in where it has none."""
    corners = []
    ramps_file = DATA / "ramps.json"
    if ramps_file.exists():
        for lat, lng, a, b in json.loads(ramps_file.read_text()).get("corners", []):
            if "Dead End" not in (a, b):
                corners.append((lat, lng, f"{a} & {b}"))
    osm = [(*graph.coords[int(n)], " & ".join(names[:2])) for n, names in graph.streets.items()]
    return corners + osm


def label_spot(lat, lng, corners, amenities):
    """The nearest named corner, or failing that the nearest named place
    (e.g. a park), so the gap finder can say where a spot is in words."""
    near = label(lat, lng, corners)
    if near:
        return near
    named = [(distance_m(lat, lng, p["lat"], p["lng"]), p["name"]) for p in amenities if p["name"]]
    d, name = min(named, default=(None, None))
    return name if d is not None and d <= MAX_PLACE_LABEL_M else None


def label(lat, lng, corners):
    """The nearest named corner within MAX_LABEL_M, or None. Ramp corners
    come first in the list, so on a tie their names win."""
    best, best_d = None, MAX_LABEL_M
    for corner_lat, corner_lng, name in corners:
        if abs(corner_lat - lat) > 0.004 or abs(corner_lng - lng) > 0.005:
            continue  # quick skip before the exact distance
        d = distance_m(lat, lng, corner_lat, corner_lng)
        if d < best_d:
            best, best_d = name, d
    return best


def outline(ring):
    return [[round(lat, OUTLINE_DECIMALS), round(lng, OUTLINE_DECIMALS)] for lat, lng in ring]


def main():
    started = time.time()
    graph = WalkGraph.from_file(DATA / "walk_graph.npz")
    amenities = load_amenities(DATA / "amenities.json")
    places = PlaceIndex(amenities)
    corners = named_corners(graph)
    if not corners:
        print("No street names found, so spots are given as coordinates. Run python scripts/build_ramps.py to add them.")
    boroughs = load_boroughs()
    names = sorted(boroughs)
    water = load_water()
    parks = load_parks()

    # Which square is in which borough, on land, and mostly in a park.
    origin, lats, lngs = lattice(boroughs)
    which = np.full((len(lats), len(lngs)), -1, dtype=np.int8)
    for b, name in enumerate(names):
        which[inside(lived_on(boroughs[name]), lats, lngs)] = b
    which[shapes_inside(water, lats, lngs)] = -1
    in_park = park_share(parks, lats, lngs) >= PARK_SHARE
    rows, cols = np.nonzero(which >= 0)
    print(f"{len(rows):,} squares of {CELL_M} m on land ({time.time() - started:.0f} s)")

    # Snap each square to the graph, as a click would.
    cells = []  # (row, col, borough index, start node, minutes left to walk)
    for row, col in zip(rows.tolist(), cols.tolist()):
        node, gap_m = graph.nearest_node(lats[row], lngs[col])
        if gap_m <= MAX_START_GAP_M:
            cells.append((row, col, int(which[row, col]), node, round(MINUTES - gap_m / WALK_SPEED_M_PER_MIN, 1)))
    n = len(cells)
    print(f"{n:,} squares within {MAX_START_GAP_M} m of a street or path")

    # Which squares start at each node, so a walk's reach can be turned into squares.
    start_nodes = np.array([c[3] for c in cells], dtype=np.int64)
    order = np.argsort(start_nodes, kind="stable")
    sorted_nodes = start_nodes[order]

    # Pass 1: walk from every square. Keep each category's score and whether
    # anything is in reach, plus which other squares the walk reaches.
    scores = np.zeros((n, len(CATEGORIES)), dtype=np.uint8)
    none_near = np.zeros((n, len(CATEGORIES)), dtype=bool)
    reached = []
    for i, (row, col, _, node, budget) in enumerate(cells):
        times = graph.reachable_within(node, budget)
        result = score_walk(places.reachable(times, MINUTES - budget))
        by_category = {c["category"]: c for c in result["categories"]}
        scores[i] = [by_category[c]["score"] for c in CATEGORIES]
        none_near[i] = [by_category[c]["count"] == 0 for c in CATEGORIES]
        nodes = np.fromiter(times.keys(), dtype=np.int64, count=len(times))
        lo = np.searchsorted(sorted_nodes, nodes, side="left")
        hi = np.searchsorted(sorted_nodes, nodes, side="right")
        hit = hi > lo
        lo, hi = lo[hit], hi[hit]
        # Every position from lo to hi, for each reached node.
        spans = np.repeat(lo - np.cumsum(np.concatenate([[0], (hi - lo)[:-1]])), hi - lo) + np.arange((hi - lo).sum())
        reached.append(order[spans].astype(np.int32))
        if (i + 1) % 5000 == 0:
            print(f"  {i + 1:,} of {n:,} squares walked ({time.time() - started:.0f} s)")

    park = np.array([in_park[c[0], c[1]] for c in cells])
    borough = np.array([c[2] for c in cells])
    print(f"{park.sum():,} squares mostly inside parks, left out of gaps and ranks")

    # Pass 2: per borough and category, the gap squares, and the square whose
    # walk reaches the most of them. Walking works both ways, so a new place
    # there would be within 15 minutes of each of those gap squares. A new
    # place goes where people are, so park squares aren't candidates.
    gaps = {name: {} for name in names}
    for k, category in enumerate(CATEGORIES):
        is_gap = none_near[:, k] & ~park
        fixes = np.array([is_gap[r].sum() for r in reached]) if is_gap.any() else np.zeros(n, dtype=int)
        fixes[park] = 0
        for b, name in enumerate(names):
            mine = borough == b
            best = None
            if (fixes[mine] > 0).any():
                i = int(np.flatnonzero(mine)[np.argmax(fixes[mine])])
                lat, lng = float(lats[cells[i][0]]), float(lngs[cells[i][1]])
                best = {
                    "lat": round(lat, 6),
                    "lng": round(lng, 6),
                    "fixes": int(fixes[i]),
                    "near": label_spot(lat, lng, corners, amenities),
                }
            gaps[name][category] = {"cells": int((is_gap & mine).sum()), "best": best}
        print(f"  {category:9} " + ", ".join(f"{name} {gaps[name][category]['cells']:,}" for name in names) + " gap squares")

    # One file per borough. Each square is 9 numbers in a flat list: its
    # column and row on the grid, its score in each category, and flags
    # (bit k: nothing of category k in reach; bit 6: mostly park).
    flags = (none_near * (1 << np.arange(len(CATEGORIES)))).sum(axis=1) + park * PARK_BIT
    for b, name in enumerate(names):
        mine = np.flatnonzero(borough == b)
        flat = np.column_stack([
            [cells[i][1] for i in mine],
            [cells[i][0] for i in mine],
            scores[mine],
            flags[mine],
        ]).astype(int).ravel().tolist()
        in_borough = boroughs[name]

        def here(rings):
            """Is a shape's first point in this borough? Each outline goes in one file."""
            return bool(inside(in_borough, np.array([rings[0][0][0]]), np.array([rings[0][0][1]]))[0, 0])

        out = DATA / f"grid-{slug(name)}.json"
        out.write_text(json.dumps({
            "meta": {
                "borough": name,
                "built": date.today().isoformat(),
                "cell_m": CELL_M,
                "minutes": MINUTES,
                "mode": "walk",
                "categories": CATEGORIES,
                # Square (col, row) has its center at origin + (col + 0.5, row + 0.5) steps.
                "origin": [round(float(origin[0]), 7), round(float(origin[1]), 7)],
                "step": [STEP_LAT, STEP_LNG],
                "cell_count": int(len(mine)),
                "outside_park_count": int((~park[mine]).sum()),
                "cell_format": "col, row, score per category, flags (bit k: no category k in reach; bit 6: park)",
            },
            "cells": flat,
            "gaps": gaps[name],
            # Outlines for the map to leave blank: parks (gap finder only) and lakes (both maps).
            "parks": [outline(ring) for rings in parks if here([rings[0]]) for ring in rings],
            "water": [outline(shape[0]) for shape in water if here(shape)],
        }, separators=(",", ":")))
        print(f"Saved {len(mine):,} squares to {out} ({out.stat().st_size / 1000:.0f} KB)")
    print(f"Done in {time.time() - started:.0f} s")


if __name__ == "__main__":
    main()
