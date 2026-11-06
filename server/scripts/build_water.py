"""Download the city's lakes, ponds, and reservoirs from OpenStreetMap.

Run once from the server folder, with the virtual environment active:
    python scripts/build_water.py

It writes data/water.json. The server cuts these out of every walking area
and turns away clicks that land on them. The rivers and bays are already
handled by trimming to the shoreline (geo/boroughs.json), so they're skipped
there. The download is shared with build_amenities.py (scripts/osm_places.py).

It also writes data/waterways.json: the named rivers, canals, bays, and
straits inside the city's limits, so a click in one can say which ("That's
in the East River", card 15).
"""

import json
import sys
from pathlib import Path

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
# Named water kept in waterways.json: rivers and canals mapped as areas,
# and bays and straits.
WATERWAY_TYPES = {"river", "canal", "stream", "tidal_channel"}
WATERWAY_NATURAL = {"bay", "strait"}

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

    water, waterways = [], []
    for _, row in features.iterrows():
        name = text(row.get("name"))
        if name and (has_tag(row, "natural", list(WATERWAY_NATURAL)) or text(row.get("water")) in WATERWAY_TYPES):
            geom = polygons_only(row.geometry.intersection(city))
            if not geom.is_empty:
                waterways.append({"name": name, "geometry": mapping(geom.simplify(0.0001))})  # about 10 m
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

    WATERWAYS_FILE.write_text(json.dumps(waterways, separators=(",", ":")))
    size_kb = WATERWAYS_FILE.stat().st_size / 1000
    print(f"\nSaved {len(waterways)} rivers, bays, and straits to {WATERWAYS_FILE} ({size_kb:.0f} KB)")
    print("Named:", ", ".join(sorted({w["name"] for w in waterways})))


if __name__ == "__main__":
    main()
