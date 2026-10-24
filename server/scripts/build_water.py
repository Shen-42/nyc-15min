"""Download the lakes, ponds, and reservoir inside Manhattan from OpenStreetMap.

Run once from the server folder, with the virtual environment active:
    python scripts/build_water.py

It writes data/water.json. The server cuts these out of every walking area
and turns away clicks that land on them. The rivers around the island are
already handled by trimming to the shoreline, so they're skipped here.
"""

import json
import sys
from pathlib import Path

import osmnx as ox
from shapely.geometry import mapping

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))
from walk_area import load_land, polygons_only  # noqa: E402

import overpass  # noqa: E402  scripts/overpass.py: server choice and retries

LAND_FILE = SERVER_DIR / "data" / "manhattan-boundary.json"
OUTPUT_FILE = SERVER_DIR / "data" / "water.json"

TAGS = {"natural": "water", "landuse": "reservoir"}
SKIP_WATER_TYPES = {"river", "canal", "stream"}

# Ignore fountains and small decorative pools.
MIN_AREA_M2 = 500
# About 111 km per degree of latitude and 84 km per degree of longitude in Manhattan.
M2_PER_SQ_DEGREE = 111_000 * 84_000


def text(value):
    return value if isinstance(value, str) else None


def main():
    overpass.configure()

    land = load_land(LAND_FILE)
    # Ask for a plain rectangle around Manhattan, which servers answer much
    # faster than the detailed shoreline. Lakes outside Manhattan (in New
    # Jersey or the Bronx) are dropped below when each one is cut to the shoreline.
    west, south, east, north = land.bounds
    print("Downloading lakes and ponds around Manhattan...")
    features = overpass.download("lakes and ponds", lambda: ox.features_from_bbox((west, south, east, north), tags=TAGS))
    features = features[features.geom_type.isin(["Polygon", "MultiPolygon"])]

    water = []
    for _, row in features.iterrows():
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
