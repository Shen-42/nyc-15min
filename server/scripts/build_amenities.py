"""Download the places people walk to, and attach each one to the walking graph (card 5).

Run once from the server folder, with the virtual environment active:
    python scripts/build_amenities.py

It writes data/amenities.json. Each category is a separate Overpass request,
and OSMnx caches each answer in ./cache, so if one request fails you can run
the script again and only the missing ones are downloaded.
"""

import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

import osmnx as ox
import shapely
from shapely import STRtree
from shapely.geometry import Point

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))
from graph import WalkGraph  # noqa: E402
from walk_area import load_land  # noqa: E402

import overpass  # noqa: E402  scripts/overpass.py: server choice and retries

GRAPH_FILE = SERVER_DIR / "data" / "walk_graph.json"
LAND_FILE = SERVER_DIR / "data" / "manhattan-boundary.json"
OUTPUT_FILE = SERVER_DIR / "data" / "amenities.json"
# Park outlines (card 12). Nobody lives in a park, so the Manhattan grid
# leaves them out of gaps and ranks, and the heat map leaves them blank.
PARKS_FILE = SERVER_DIR / "data" / "parks.json"
# Outlines are simplified to about this many meters, to keep the file small.
PARK_SIMPLIFY_M = 5


def text(value):
    return value if isinstance(value, str) else None


def is_subway(row):
    # railway=station also matches commuter rail and PATH. Keep NYC subway stations.
    subway = text(row.get("station")) == "subway" or text(row.get("subway")) == "yes"
    return subway and "PATH" not in (text(row.get("network")) or "")


# OpenStreetMap tags for each category. A place matches if it has any of them.
CATEGORIES = {
    # Full grocery stores only. Bodegas (shop=convenience) are on almost every
    # block, so counting them would give every point in Manhattan full marks.
    "grocery": {"tags": {"shop": ["supermarket", "grocery", "greengrocer"]}},
    "pharmacy": {"tags": {"amenity": "pharmacy", "healthcare": "pharmacy"}},
    "clinic": {"tags": {"amenity": ["clinic", "doctors", "hospital"]}},
    "park": {"tags": {"leisure": "park"}},
    "school": {"tags": {"amenity": "school"}},
    "subway": {"tags": {"railway": "station"}, "keep": is_subway},
}

# Seconds to wait between the six category downloads.
PAUSE_BETWEEN_S = 10

# Parks smaller than this are traffic islands and sitting areas, not parks.
MIN_PARK_M2 = 1_000

# A point place (a shop, a station) farther than this from any street or path
# is dropped, since we couldn't route a walk to it anyway.
MAX_SNAP_M = 150

# A place drawn as an area (a park, a school campus) is reached when you reach
# any path inside it or within this many meters of its edge.
EDGE_M = 20

# Work in meters around Manhattan's middle so distances are real distances.
LAT0, LNG0 = 40.78, -73.97
M_PER_DEG_LAT = 110_540
M_PER_DEG_LNG = 111_320 * math.cos(math.radians(LAT0))


def to_meters(geom):
    def f(lnglat):
        out = lnglat.copy()
        out[:, 0] = (lnglat[:, 0] - LNG0) * M_PER_DEG_LNG
        out[:, 1] = (lnglat[:, 1] - LAT0) * M_PER_DEG_LAT
        return out

    return shapely.transform(geom, f)


def main():
    overpass.configure()

    land = load_land(LAND_FILE)
    west, south, east, north = land.bounds

    # A spatial index over every graph node, for fast nearest-node lookups.
    graph = WalkGraph.from_file(GRAPH_FILE)
    node_ids = list(graph.coords)
    node_points = [to_meters(Point(lng, lat)) for lat, lng in graph.coords.values()]
    tree = STRtree(node_points)

    def nearest_node(point_m):
        idx, dist = tree.query_nearest(point_m, max_distance=MAX_SNAP_M, return_distance=True)
        return (node_ids[idx[0]], float(dist[0])) if len(idx) else (None, None)

    amenities = []
    park_outlines = []
    for category, spec in CATEGORIES.items():
        print(f"\n--- {category} ---")
        if category != next(iter(CATEGORIES)):
            time.sleep(PAUSE_BETWEEN_S)  # be gentle with the shared server
        features = overpass.download(category, lambda: ox.features_from_bbox((west, south, east, north), tags=spec["tags"]))
        keep = spec.get("keep")
        kept = 0
        for (element, osm_id), row in features.iterrows():
            if keep and not keep(row):
                continue
            geom = row.geometry
            if geom.geom_type not in ("Point", "Polygon", "MultiPolygon"):
                continue
            spot = geom if geom.geom_type == "Point" else geom.representative_point()
            if not land.contains(spot):
                continue  # in New Jersey, Queens, or the Bronx

            if geom.geom_type == "Point":
                node, _ = nearest_node(to_meters(spot))
                nodes = [node] if node is not None else []
            else:
                area_m = to_meters(geom)
                if category == "park" and area_m.area < MIN_PARK_M2:
                    continue
                if category == "park":
                    simple = geom.simplify(PARK_SIMPLIFY_M / M_PER_DEG_LAT)
                    parts = list(simple.geoms) if simple.geom_type == "MultiPolygon" else [simple]
                    parts = [part for part in parts if part.geom_type == "Polygon" and not part.is_empty]
                    park_outlines.append({
                        "name": text(row.get("name")),
                        "area_m2": round(area_m.area),
                        # Outer rings as [lat, lng]. Holes (a building inside a park) are ignored.
                        "rings": [[[round(y, 6), round(x, 6)] for x, y in part.exterior.coords] for part in parts],
                    })
                inside = tree.query(area_m.buffer(EDGE_M), predicate="contains")
                nodes = [node_ids[i] for i in inside]
                if not nodes:
                    # A small school building with no path inside: use the nearest street.
                    node, _ = nearest_node(to_meters(spot))
                    nodes = [node] if node is not None else []
            if not nodes:
                continue

            amenities.append({
                "id": f"{element}/{osm_id}",
                "category": category,
                "name": text(row.get("name")),
                "lat": round(spot.y, 6),
                "lng": round(spot.x, 6),
                "nodes": nodes,  # graph nodes that count as reaching this place
            })
            # OpenStreetMap opening hours, when listed (card 10). Left out
            # when missing, to keep the file small.
            hours = text(row.get("opening_hours"))
            if hours:
                amenities[-1]["hours"] = hours
            kept += 1
        print(f"Kept {kept} {category} places in Manhattan")

    OUTPUT_FILE.write_text(json.dumps(amenities, separators=(",", ":")))
    PARKS_FILE.write_text(json.dumps(park_outlines, separators=(",", ":")))
    print(f"Saved {len(park_outlines)} park outlines to {PARKS_FILE} ({PARKS_FILE.stat().st_size / 1000:.0f} KB)")
    counts = Counter(a["category"] for a in amenities)
    size_mb = OUTPUT_FILE.stat().st_size / 1_000_000
    print(f"\nSaved {len(amenities)} places to {OUTPUT_FILE} ({size_mb:.1f} MB)")
    with_hours = Counter(a["category"] for a in amenities if "hours" in a)
    for category in CATEGORIES:
        print(f"  {category:9} {counts[category]:5}  ({with_hours[category]} with opening hours)")


if __name__ == "__main__":
    main()
