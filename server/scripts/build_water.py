"""Download the city's lakes, ponds, and reservoirs from OpenStreetMap.

Run once from the server folder, with the virtual environment active:
    python scripts/build_water.py

It writes data/water.json. The server cuts these out of every walking area
and turns away clicks that land on them. The rivers and bays are already
handled by trimming to the shoreline (geo/boroughs.json), so they're skipped
there. The download is shared with build_amenities.py (scripts/osm_places.py).

It also writes data/waterways.json: the named rivers, canals, bays, and
straits inside the city's limits, so a click in one can say which ("That's
in the East River", card 15). That's a second, separate download, of the
whole area inside the city's limits, water included: the big rivers and
bays have no outline in OpenStreetMap, since they're part of the sea there.
Only their center lines (the Hudson, the East River) or a single label
point (Jamaica Bay) carry the name, out in the water where the first
download, of the land, doesn't reach.
"""

import json
import sys
from collections import Counter
from pathlib import Path

import osmnx as ox
import shapely
from shapely.geometry import Polygon, mapping

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))
from walk_area import load_land, polygons_only  # noqa: E402

import osm_places  # noqa: E402  scripts/osm_places.py: the one download
import overpass  # noqa: E402  scripts/overpass.py: server choice and retries
from osm_places import has_tag, text  # noqa: E402

OUTPUT_FILE = SERVER_DIR / "data" / "water.json"
WATERWAYS_FILE = SERVER_DIR / "data" / "waterways.json"
# The city's limits, water included (scripts/make_city_outline.py).
CITY_OUTLINE_FILE = SERVER_DIR / "geo" / "city-outline.json"

TAGS = {"natural": "water", "landuse": "reservoir"}
SKIP_WATER_TYPES = {"river", "canal", "stream"}
# Named water kept in waterways.json: rivers and canals mapped as areas or
# as center lines, and bays and straits as areas or label points.
WATERWAY_TAGS = {"natural": ["water", "bay", "strait"], "waterway": ["river", "canal", "tidal_channel"]}
WATER_TYPES = {"river", "canal", "tidal_channel"}  # water=* on an area
LINE_TYPES = {"river", "canal", "tidal_channel"}  # waterway=* on a line
BAY_TYPES = ["bay", "strait"]  # natural=* on an area or a point
# River center lines are kept this far outside the city's limits too: the
# limits run down the middle of the Hudson, right along its center line, so
# cutting the line to them strictly left almost none of it.
LINE_MARGIN_DEGREES = 0.01
# Names misspelled in OpenStreetMap (fix them there too, when you can).
NAME_FIXES = {"Big Channelv": "Big Channel"}

# Ignore fountains and small decorative pools.
MIN_AREA_M2 = 500
# About 111 km per degree of latitude and 84 km per degree of longitude in New York.
M2_PER_SQ_DEGREE = 111_000 * 84_000


def main():
    overpass.configure()

    land = load_land()
    # Lakes outside the city (in New Jersey or Nassau County) are dropped
    # below when each one is cut to the shoreline.
    print("Downloading lakes and ponds for the whole city...")
    features = osm_places.download(land)
    features = features[features.geom_type.isin(["Polygon", "MultiPolygon"])]

    rings = json.loads(CITY_OUTLINE_FILE.read_text())["rings"]
    city = shapely.make_valid(shapely.union_all([Polygon([(lng, lat) for lat, lng in r]) for r in rings]))

    water = []
    for _, row in features.iterrows():
        if not any(has_tag(row, key, value) for key, value in TAGS.items()):
            continue  # a park, school, or shop from the shared download
        if text(row.get("water")) in SKIP_WATER_TYPES:
            continue
        geom = polygons_only(row.geometry.intersection(land))
        if geom.is_empty or geom.area * M2_PER_SQ_DEGREE < MIN_AREA_M2:
            continue
        water.append({
            "name": text(row.get("name")),
            "geometry": mapping(geom.simplify(0.00001)),  # about 1 m of detail
        })

    OUTPUT_FILE.write_text(json.dumps(water, separators=(",", ":")))
    named = sorted({w["name"] for w in water if w["name"]})
    print(f"Saved {len(water)} bodies of water to {OUTPUT_FILE}")
    print("Named:", ", ".join(named))

    print("\nDownloading the names of the rivers and bays...")
    named = overpass.download("rivers and bays", lambda: ox.features_from_polygon(city.simplify(0.001), tags=WATERWAY_TAGS))
    # Something on the line between two download pieces comes back from both.
    named = named[~named.index.duplicated()]
    near_city = city.buffer(LINE_MARGIN_DEGREES)
    waterways = []
    for _, row in named.iterrows():
        name = text(row.get("name"))
        geom = row.geometry
        if not name or geom is None:
            continue
        name = NAME_FIXES.get(name, name)
        if text(row.get("tunnel")) not in (None, "no"):
            continue  # a tunnel under the water, like the Gowanus flushing tunnel
        # kind tells the server how to use it (walk_area.NearestName): an
        # area to be inside, a river or channel line, or a bay's label point.
        shape_type = geom.geom_type
        if shape_type in ("Polygon", "MultiPolygon"):
            keep = has_tag(row, "natural", BAY_TYPES) or text(row.get("water")) in WATER_TYPES
            kind, clipped = "area", polygons_only(geom.intersection(city))
        elif shape_type in ("LineString", "MultiLineString"):
            waterway = text(row.get("waterway"))
            keep = waterway in LINE_TYPES
            kind, clipped = ("river" if waterway == "river" else "channel"), geom.intersection(near_city)
        else:  # a point
            keep = has_tag(row, "natural", BAY_TYPES)
            kind, clipped = "label", geom.intersection(city)
        if not keep or clipped.is_empty:
            continue  # a lake, a stream, or outside the city
        waterways.append({"name": name, "kind": kind, "geometry": mapping(clipped.simplify(0.0001))})  # about 10 m

    WATERWAYS_FILE.write_text(json.dumps(waterways, separators=(",", ":")))
    size_kb = WATERWAYS_FILE.stat().st_size / 1000
    kinds = Counter(w["kind"] for w in waterways)
    print(f"\nSaved {len(waterways)} rivers, bays, and straits to {WATERWAYS_FILE} ({size_kb:.0f} KB): "
          + ", ".join(f"{n} {k}" for k, n in kinds.items()))
    print("Named:", ", ".join(sorted({w["name"] for w in waterways})))


if __name__ == "__main__":
    main()
