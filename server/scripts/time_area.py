"""Time drawing the walking area two ways (card 15).

Run from the server folder with the server's packages installed:
    python scripts/time_area.py

For a spot in each borough it draws the area the old way, widening every
street with shapely and joining the results (draw() below, timing each
step), then the way walk_area.py does now, on a grid of squares in NumPy.
It says how long each took and how much the shape moved (as a share of its
area). On Nov 4 the old way took 64-125 ms on a laptop, almost all of it
widening and joining; snapping, straightening, or merging the streets first
didn't help.
"""

import math
import sys
import time
from pathlib import Path

import shapely
from shapely.geometry import LineString, MultiLineString, box, shape
from shapely.ops import unary_union

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))
from graph import WALK_SPEED_M_PER_MIN, WalkGraph  # noqa: E402
from walk_area import (  # noqa: E402
    BUFFER_M,
    M_PER_DEG_LAT,
    QUAD_SEGS,
    SIMPLIFY_M,
    cut_path,
    fill_holes,
    load_land,
    load_water,
    polygons_only,
    walking_area,
)

DATA = SERVER_DIR / "data"
SPOTS = {
    "Manhattan": (40.7580, -73.9855),
    "Brooklyn": (40.6782, -73.9442),
    "Queens": (40.7590, -73.8303),
    "Bronx": (40.8448, -73.8648),
    "Staten Island": (40.6437, -74.0764),
}
MINUTES = 15
REPEATS = 3

# Ways to draw it: the old one, then the grid at two square sizes.
TRIES = {
    "widen each street (old)": None,
    "grid of 5 m squares": 5,
    "grid of 10 m squares (now)": 10,
}


def draw(graph, start, times, land, options, steps):
    """The old walk_area.walking_area, with timings in steps and options to
    try: "grid", "straighten", "merge", "clip"."""
    t = time.perf_counter()

    def lap(name):
        nonlocal t
        now = time.perf_counter()
        steps[name] = steps.get(name, 0) + (now - t) * 1000
        t = now

    lat0, lng0 = graph.coords[start]
    m_per_deg_lng = 111_320 * math.cos(math.radians(lat0))

    def path_xy(u, v):
        return [((lng - lng0) * m_per_deg_lng, (lat - lat0) * M_PER_DEG_LAT) for lat, lng in graph.edge_points(u, v)]

    segments, done = [], set()
    for u, minutes in times.items():
        for v, length_m in graph.neighbors(u):
            if v in times:
                key = (min(u, v), max(u, v))
                if key in done:
                    continue
                done.add(key)
                segments.append(path_xy(u, v))
            else:
                meters_left = (MINUTES - minutes) * WALK_SPEED_M_PER_MIN
                if meters_left <= 0 or length_m <= 0:
                    continue
                segments.append(cut_path(path_xy(u, v), min(meters_left / length_m, 1.0)))
    segments = [s for s in segments if len(s) >= 2 and s[0] != s[-1]]
    lap("paths")

    lines = [LineString(s) for s in segments]
    if "merge" in options:
        merged = shapely.line_merge(MultiLineString(lines))
        lines = list(getattr(merged, "geoms", [merged]))
    if "straighten" in options:
        lines = list(shapely.simplify(lines, 2))
    widened = shapely.buffer(lines, BUFFER_M, quad_segs=QUAD_SEGS)
    lap("widen")
    joined = shapely.union_all(widened, grid_size=1 if "grid" in options else None)
    lap("join")
    shape = fill_holes(joined).simplify(SIMPLIFY_M)
    lap("fill and simplify")

    def to_lnglat(xy):
        out = xy.copy()
        out[:, 0] = lng0 + xy[:, 0] / m_per_deg_lng
        out[:, 1] = lat0 + xy[:, 1] / M_PER_DEG_LAT
        return out

    area = shapely.transform(shape, to_lnglat)
    lap("to degrees")
    if "clip" in options:
        nearby = shapely.make_valid(shapely.clip_by_rect(land, *area.bounds))
    else:
        nearby = land.intersection(box(*area.bounds))
    lap("cut shoreline to box")
    area = polygons_only(area.intersection(nearby))
    lap("trim to land")
    return area


def main():
    started = time.perf_counter()
    graph = WalkGraph.from_file(DATA / "walk_graph.npz")
    land = load_land()
    water = load_water(DATA / "water.json")
    land = land.difference(unary_union([s for _, s in water]))  # as main.py does
    print(f"Loaded in {time.perf_counter() - started:.1f} s. Land has {shapely.get_num_coordinates(land):,} points.")
    print(f"Times are the best of {REPEATS}, in ms.\n")

    totals = {name: 0.0 for name in TRIES}
    for borough, (lat, lng) in SPOTS.items():
        start, _ = graph.nearest_node(lat, lng)
        times = graph.reachable_within(start, MINUTES)
        print(f"{borough}: {len(times):,} corners reached")
        base = None
        for name, cell_m in TRIES.items():
            best_total, best_steps, area = math.inf, None, None
            for _ in range(REPEATS):
                steps = {}
                if cell_m is None:
                    area = draw(graph, start, times, land, set(), steps)
                else:
                    t = time.perf_counter()
                    area = shape(walking_area(graph, start, times, MINUTES, WALK_SPEED_M_PER_MIN, land, cell_m=cell_m))
                    steps["all"] = (time.perf_counter() - t) * 1000
                if sum(steps.values()) < best_total:
                    best_total, best_steps = sum(steps.values()), steps
            totals[name] += best_total
            if base is None:
                base = area
                print(f"  {name:28} {best_total:6.0f}  (" + ", ".join(f"{k} {v:.0f}" for k, v in best_steps.items()) + ")")
            else:
                moved = base.symmetric_difference(area).area / base.area * 100
                print(f"  {name:28} {best_total:6.0f}  shape moved {moved:.2f}%, {shapely.get_num_coordinates(area):,} points (old {shapely.get_num_coordinates(base):,})")
        print()
    print("All five spots:")
    for name, total in totals.items():
        print(f"  {name:28} {total:6.0f} ms")


if __name__ == "__main__":
    main()
