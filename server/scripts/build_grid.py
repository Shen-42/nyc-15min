"""Score every 100 m of Manhattan, and find the gaps (card 12).

Run from the server folder after the other build scripts:
    python scripts/build_grid.py

For each cell of a 100 m grid on land, it runs the same 15-minute walk as
the site (walking, any time) and saves each category's score. Then, for each
category, it finds the cells with no such place in reach ("gaps") and the
one cell where a new place would put the most gap cells within 15 minutes.

It writes data/grid.json. The monthly refresh job runs it after the
downloads. It needs only the standard library, plus the server's own
graph.py, amenities.py, and scoring.py. It takes under a minute.
"""

import json
import math
import sys
import time
from array import array
from collections import defaultdict
from datetime import date
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))
from amenities import load_amenities, reachable_amenities  # noqa: E402
from graph import WALK_SPEED_M_PER_MIN, WalkGraph, distance_m  # noqa: E402
from scoring import CATEGORY_SETTINGS, score_walk  # noqa: E402

DATA = SERVER_DIR / "data"
OUTPUT_FILE = DATA / "grid.json"

CELL_M = 100
MINUTES = 15
# The same limits as the site (main.py): a cell whose center is farther than
# this from any path (a rail yard, the middle of a pier) is left out.
MAX_START_GAP_M = 150
# The land the map lets you click on (see build_graph.py).
LAND = ["main", "roosevelt"]
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
# Parks at least this big are cut out of the heat map and gap finder image,
# so they show blank with clean edges. 0 means every park; the lakes are
# always cut out.
BLANK_MIN_M2 = 0

CATEGORIES = list(CATEGORY_SETTINGS)

# Meters around Manhattan's middle, as in the other scripts.
LAT0, LNG0 = 40.78, -73.97
M_PER_DEG_LAT = 110_540
M_PER_DEG_LNG = 111_320 * math.cos(math.radians(LAT0))


def inside_ring(lat, lng, ring):
    """Ray casting: is the point inside a ring of (lat, lng) points?"""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def water_polygons():
    """Lakes and ponds as lists of rings in (lat, lng): [outer, hole, hole, ...]."""
    polygons = []
    for item in json.loads((DATA / "water.json").read_text()):
        geom = item["geometry"]
        parts = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for rings in parts:
            polygons.append([[(lat, lng) for lng, lat in ring] for ring in rings])
    return polygons


def on_land(lat, lng, land, water):
    if not any(inside_ring(lat, lng, ring) for ring in land):
        return False
    for outer, *holes in water:
        if inside_ring(lat, lng, outer) and not any(inside_ring(lat, lng, h) for h in holes):
            return False
    return True


def grid_points(land, water):
    lats = [lat for ring in land for lat, _ in ring]
    lngs = [lng for ring in land for _, lng in ring]
    step_lat = CELL_M / M_PER_DEG_LAT
    step_lng = CELL_M / M_PER_DEG_LNG
    points = []
    lat = min(lats) + step_lat / 2
    while lat < max(lats):
        lng = min(lngs) + step_lng / 2
        while lng < max(lngs):
            if on_land(lat, lng, land, water):
                points.append((round(lat, 6), round(lng, 6)))
            lng += step_lng
        lat += step_lat
    return points


def named_corners(graph, streets):
    """[(lat, lng, "Street & Street")] to describe a spot by its cross streets.
    The curb ramp data names both streets at almost every corner.
    OpenStreetMap's own names, from the graph, fill in where it has none
    (Roosevelt Island, for one); there are few of them, since in Manhattan
    many sidewalks are mapped as separate, unnamed paths."""
    corners = []
    ramps_file = DATA / "ramps.json"
    if ramps_file.exists():
        for lat, lng, a, b in json.loads(ramps_file.read_text()).get("corners", []):
            if "Dead End" not in (a, b):
                corners.append((lat, lng, f"{a} & {b}"))
    osm = [(*graph.coords[int(n)], " & ".join(names[:2])) for n, names in streets.items()]
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


def load_parks():
    """Park outer rings as (ring, bounding box, area in m²)."""
    parks_file = DATA / "parks.json"
    if not parks_file.exists():
        sys.exit("No park outlines yet. Run python scripts/build_amenities.py first.")
    parks = []
    for park in json.loads(parks_file.read_text()):
        for ring in park["rings"]:
            lats = [lat for lat, _ in ring]
            lngs = [lng for _, lng in ring]
            parks.append((ring, (min(lats), max(lats), min(lngs), max(lngs)), park["area_m2"]))
    return parks


def park_checker(parks):
    """A function telling whether most of a grid square lies inside parks."""
    half_lat = CELL_M / 2 / M_PER_DEG_LAT
    half_lng = CELL_M / 2 / M_PER_DEG_LNG
    offsets = [(i + 0.5) / PARK_SAMPLES * 2 - 1 for i in range(PARK_SAMPLES)]  # -2/3, 0, 2/3

    def in_any_park(lat, lng):
        return any(
            box[0] <= lat <= box[1] and box[2] <= lng <= box[3] and inside_ring(lat, lng, ring)
            for ring, box, _ in parks
        )

    def in_park(lat, lng):
        points = [(lat + dy * half_lat, lng + dx * half_lng) for dy in offsets for dx in offsets]
        inside = sum(1 for p in points if in_any_park(*p))
        return inside >= PARK_SHARE * len(points)

    return in_park


def blank_rings(parks, water):
    """Outlines the map leaves blank: big parks and the lakes, as [[lat, lng], ...]."""
    rings = [ring for ring, _, area in parks if area >= BLANK_MIN_M2]
    rings += [[[round(lat, 6), round(lng, 6)] for lat, lng in polygon[0]] for polygon in water]
    return rings


def main():
    started = time.time()
    graph_data = json.loads((DATA / "walk_graph.json").read_text())
    graph = WalkGraph(graph_data["nodes"], graph_data["edges"])
    corners = named_corners(graph, graph_data.get("streets", {}))
    if not corners:
        print("No street names found, so spots are given as coordinates.")
        print("Run python scripts/build_ramps.py to add them.")
    amenities = load_amenities(DATA / "amenities.json")
    boundary = json.loads((DATA / "manhattan-boundary.json").read_text())
    land = [boundary[name] for name in LAND]
    water = water_polygons()

    points = grid_points(land, water)
    print(f"{len(points):,} cells of {CELL_M} m on land")
    parks = load_parks()
    in_park = park_checker(parks)

    # Snap each cell to the graph, as a click would.
    snapped = []  # (cell index, start node, minutes left to walk)
    node_cells = defaultdict(list)
    for i, (lat, lng) in enumerate(points):
        node, gap_m = graph.nearest_node(lat, lng)
        if gap_m > MAX_START_GAP_M:
            continue
        budget = round(MINUTES - gap_m / WALK_SPEED_M_PER_MIN, 1)
        snapped.append((i, node, budget))
        node_cells[node].append(i)
    print(f"{len(snapped):,} cells within {MAX_START_GAP_M} m of a street or path")

    # Pass 1: walk from every cell. Keep each category's score and whether
    # anything is in reach, plus which other cells the walk reaches.
    cells = []
    reached_cells = {}
    keep = {}  # cell index -> position in `cells`
    for n, (i, node, budget) in enumerate(snapped):
        times = graph.reachable_within(node, budget)
        result = score_walk(reachable_amenities(amenities, times, MINUTES - budget))
        by_category = {c["category"]: c for c in result["categories"]}
        lat, lng = points[i]
        keep[i] = len(cells)
        cells.append([
            lat,
            lng,
            [by_category[c]["score"] for c in CATEGORIES],
            [round(by_category[c]["nearest"][0]["minutes"], 1) if by_category[c]["count"] else None for c in CATEGORIES],
            1 if in_park(lat, lng) else 0,
        ])
        reached_cells[i] = array("i", (j for node_id in times for j in node_cells.get(node_id, ())))
        if (n + 1) % 1000 == 0:
            print(f"  {n + 1:,} of {len(snapped):,} cells walked ({time.time() - started:.0f} s)")

    # Pass 2: for each category, the gap cells, and the cell whose walk
    # reaches the most of them. Walking works both ways, so a new place there
    # would be within 15 minutes of each of those gap cells.
    park_cells = {i for i in keep if cells[keep[i]][4]}
    print(f"{len(park_cells):,} cells mostly inside parks, left out of gaps and ranks")
    gaps = {}
    for k, category in enumerate(CATEGORIES):
        gap_cells = {i for i in keep if cells[keep[i]][3][k] is None and i not in park_cells}
        best_i, best_fixed = None, 0
        if gap_cells:
            for i, reached in reached_cells.items():
                if i in park_cells:
                    continue  # a new store goes where people are
                fixed = sum(1 for j in reached if j in gap_cells)
                if fixed > best_fixed:
                    best_i, best_fixed = i, fixed
        spot = None
        if best_i is not None:
            lat, lng = points[best_i]
            spot = {"lat": lat, "lng": lng, "fixes": best_fixed, "near": label_spot(lat, lng, corners, amenities)}
        gaps[category] = {"cells": len(gap_cells), "best": spot}
        where = f" Best spot: {spot['near'] or (spot['lat'], spot['lng'])}, fixes {spot['fixes']:,}." if spot else ""
        print(f"  {category:9} {len(gap_cells):5,} gap cells.{where}")

    OUTPUT_FILE.write_text(json.dumps({
        "meta": {
            "built": date.today().isoformat(),
            "cell_m": CELL_M,
            "minutes": MINUTES,
            "mode": "walk",
            "categories": CATEGORIES,
            "cell_count": len(cells),
            "outside_park_count": len(cells) - len(park_cells),
        },
        # [lat, lng, [score per category], [minutes to the nearest, or null], 1 if mostly park]
        "cells": cells,
        "gaps": gaps,
        # Big parks and lakes, for the map to leave blank.
        "blank": blank_rings(parks, water),
    }, separators=(",", ":")))
    size_kb = OUTPUT_FILE.stat().st_size / 1000
    print(f"Saved {len(cells):,} cells to {OUTPUT_FILE} ({size_kb:.0f} KB) in {time.time() - started:.0f} s")


if __name__ == "__main__":
    main()
