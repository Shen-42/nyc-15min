"""Download the city's lakes, ponds, and reservoirs from OpenStreetMap.

Run once from the server folder, with the virtual environment active:
    python scripts/build_water.py

It writes data/water.json. The server cuts these out of every walking area
and turns away clicks that land on them. The rivers and bays are already
handled by trimming to the shoreline (geo/boroughs.json), so they're skipped
here. The download is shared with build_amenities.py (scripts/osm_places.py).
"""

import json
import sys
from pathlib import Path

from shapely.geometry import mapping

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))
from walk_area import load_land, polygons_only  # noqa: E402

import osm_places  # noqa: E402  scripts/osm_places.py: the one download
import overpass  # noqa: E402  scripts/overpass.py: server choice and retries
from osm_places import has_tag, text  # noqa: E402

OUTPUT_FILE = SERVER_DIR / "data" / "water.json"

TAGS = {"natural": "water", "landuse": "reservoir"}
SKIP_WATER_TYPES = {"river", "canal", "stream"}

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


if __name__ == "__main__":
    main()
