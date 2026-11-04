"""Download the places people walk to, and attach each one to the walking graph (card 5).

Run once from the server folder, with the virtual environment active, after
scripts/build_graph.py:
    python scripts/build_amenities.py

It writes data/amenities.json and data/parks.json (parks, and other land
where nobody lives: cemeteries, golf courses, nature areas, airports,
prisons). Every category comes from
one download for the whole city (scripts/osm_places.py), and OSMnx caches
each piece of it in ./cache, so if a piece fails you can run the script
again and only the missing ones are downloaded.
"""

import json
import math
import sys
from collections import Counter
from pathlib import Path

import shapely
from shapely import STRtree

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))
from graph import WalkGraph  # noqa: E402
from walk_area import load_land  # noqa: E402

import osm_places  # noqa: E402  scripts/osm_places.py: the one download
import overpass  # noqa: E402  scripts/overpass.py: server choice and retries
from osm_places import has_tag, text  # noqa: E402

GRAPH_FILE = SERVER_DIR / "data" / "walk_graph.npz"
OUTPUT_FILE = SERVER_DIR / "data" / "amenities.json"
# Park outlines (card 12). Nobody lives in a park, so the grid
# leaves them out of gaps and ranks, and the heat map leaves them blank.
PARKS_FILE = SERVER_DIR / "data" / "parks.json"
# Outlines are simplified to about this many meters, to keep the file small.
PARK_SIMPLIFY_M = 5


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

# Land where nobody lives, besides parks (card 15). Their outlines go in
# parks.json with the parks, so the grid leaves them out of the gaps, the best
# spots, and the rank, and the server turns away clicks on them. A shape
# belongs to the first kind whose tags it has.
NOT_LIVED_IN = {
    "cemetery": {"landuse": "cemetery", "amenity": "grave_yard"},
    "golf course": {"leisure": "golf_course"},
    "nature area": {"leisure": "nature_reserve", "natural": "wetland"},
    "airport": {"aeroway": "aerodrome"},
    "prison": {"amenity": "prison"},
}

# Nature areas bigger than this are skipped. Some huge protected areas, like
# Gateway National Recreation Area, take in neighborhoods (Breezy Point), and
# the smaller marshes and reserves inside them are listed on their own.
MAX_NATURE_M2 = 20_000_000

# Parks smaller than this are traffic islands and sitting areas, not parks.
MIN_PARK_M2 = 1_000

# A point place (a shop, a station) farther than this from any street or path
# is dropped, since we couldn't route a walk to it anyway.
MAX_SNAP_M = 150

# A place drawn as an area (a park, a school campus) is reached when you reach
# any path inside it or within this many meters of its edge.
EDGE_M = 20

# Work in meters around Manhattan's middle so distances are real distances.
# Across the city that's off by under 1%, which only matters for the edge widths.
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


def outline(row, geom, area_m, kind):
    """A parks.json entry: name, kind, area, and outer rings as [lat, lng]."""
    simple = geom.simplify(PARK_SIMPLIFY_M / M_PER_DEG_LAT)
    parts = list(simple.geoms) if simple.geom_type == "MultiPolygon" else [simple]
    parts = [part for part in parts if part.geom_type == "Polygon" and not part.is_empty]
    return {
        "name": text(row.get("name")),
        "kind": kind,
        "area_m2": round(area_m.area),
        # Holes (a building inside a park) are ignored.
        "rings": [[[round(y, 6), round(x, 6)] for x, y in part.exterior.coords] for part in parts],
    }


def matches(row, spec):
    """Does a downloaded feature belong to this category?"""
    if not any(has_tag(row, key, values) for key, values in spec["tags"].items()):
        return False
    keep = spec.get("keep")
    return keep(row) if keep else True


def main():
    overpass.configure()

    land = load_land()

    # A spatial index over every graph node, for fast nearest-node lookups.
    graph = WalkGraph.from_file(GRAPH_FILE)
    node_ids = graph.ids.tolist()
    node_points = shapely.points((graph.lng - LNG0) * M_PER_DEG_LNG, (graph.lat - LAT0) * M_PER_DEG_LAT)
    tree = STRtree(node_points)

    def nearest_node(point_m):
        idx, dist = tree.query_nearest(point_m, max_distance=MAX_SNAP_M, return_distance=True)
        return (node_ids[idx[0]], float(dist[0])) if len(idx) else (None, None)

    print("Downloading places for the whole city...")
    features = osm_places.download(land)
    print(f"Downloaded {len(features):,} features")

    amenities = []
    park_outlines = []
    for category, spec in CATEGORIES.items():
        kept = 0
        for (element, osm_id), row in features.iterrows():
            if not matches(row, spec):
                continue
            geom = row.geometry
            if geom.geom_type not in ("Point", "Polygon", "MultiPolygon"):
                continue
            spot = geom if geom.geom_type == "Point" else geom.representative_point()
            if not land.contains(spot):
                continue  # in New Jersey, Westchester, or Nassau County

            if geom.geom_type == "Point":
                node, _ = nearest_node(to_meters(spot))
                nodes = [node] if node is not None else []
            else:
                area_m = to_meters(geom)
                if category == "park" and area_m.area < MIN_PARK_M2:
                    continue
                if category == "park":
                    park_outlines.append(outline(row, geom, area_m, "park"))
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
        print(f"Kept {kept:,} {category} places")

    # Other land where nobody lives. A nature reserve can lie mostly in the
    # water (Jamaica Bay's), so these count if any part touches land.
    shapely.prepare(land)
    other = Counter()
    for _, row in features.iterrows():
        geom = row.geometry
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        kind = next((k for k, tags in NOT_LIVED_IN.items() if any(has_tag(row, key, v) for key, v in tags.items())), None)
        if kind is None or not land.intersects(geom):
            continue
        area_m = to_meters(geom)
        if area_m.area < MIN_PARK_M2:
            continue
        if kind == "nature area" and area_m.area > MAX_NATURE_M2:
            print(f"  skipped a {area_m.area / 1e6:.0f} km² nature area: {text(row.get('name'))}")
            continue
        park_outlines.append(outline(row, geom, area_m, kind))
        other[kind] += 1
    print("Land where nobody lives, besides parks: " + ", ".join(f"{n:,} {k}" for k, n in other.items()))
    # The biggest of each kind, to check by eye that none takes in a neighborhood.
    for kind in NOT_LIVED_IN:
        biggest = sorted((o for o in park_outlines if o["kind"] == kind), key=lambda o: -o["area_m2"])[:5]
        print(f"  largest {kind}s: " + "; ".join(f"{o['name'] or '(unnamed)'} {o['area_m2'] / 1e6:.1f} km²" for o in biggest))

    OUTPUT_FILE.write_text(json.dumps(amenities, separators=(",", ":")))
    PARKS_FILE.write_text(json.dumps(park_outlines, separators=(",", ":")))
    print(f"Saved {len(park_outlines)} outlines of parks and other unlived land to {PARKS_FILE} ({PARKS_FILE.stat().st_size / 1000:.0f} KB)")
    counts = Counter(a["category"] for a in amenities)
    size_mb = OUTPUT_FILE.stat().st_size / 1_000_000
    print(f"\nSaved {len(amenities)} places to {OUTPUT_FILE} ({size_mb:.1f} MB)")
    with_hours = Counter(a["category"] for a in amenities if "hours" in a)
    for category in CATEGORIES:
        print(f"  {category:9} {counts[category]:5}  ({with_hours[category]} with opening hours)")


if __name__ == "__main__":
    main()
