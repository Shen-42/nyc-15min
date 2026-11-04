"""Make geo/city-outline.json, New York City's administrative boundary (card 15).

The map greys out everything outside the city. Cutting the grey along the
shoreline (geo/boroughs.json) also greys the rivers and bays inside the
city, and where the 2013 shoreline and the map tiles disagree (marsh islands
in Jamaica Bay, rocks in Eastchester Bay), light patches show in the water.
The city's legal boundary runs through the water instead: down the middle of
the Hudson to the New Jersey line, and out into the ocean. That's this file.

It comes from OpenStreetMap's borough boundaries (water included), the same
ones build_graph.py downloads the streets inside. Run once, from the server
folder, with the build packages installed (it makes five small requests):
    python scripts/make_city_outline.py

It writes geo/city-outline.json and a copy for the site,
client/src/data/city-outline.json. Both are committed: the boundary doesn't change.
"""

import json
import sys
from pathlib import Path

import shapely
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import overpass  # noqa: E402  scripts/overpass.py: the five boroughs' names

SERVER_DIR = Path(__file__).resolve().parent.parent
OUTPUTS = [SERVER_DIR / "geo" / "city-outline.json", SERVER_DIR.parent / "client" / "src" / "data" / "city-outline.json"]

# Straightened to within about 10 m: plenty for a grey mask, and small.
SIMPLIFY_DEGREES = 0.0001
# Specks left over where borough lines don't quite meet.
MIN_AREA_DEGREES = 1e-6


def main():
    overpass.configure()
    shapes = []
    for name in overpass.BOROUGHS:
        shape = overpass.borough_area(name)
        print(f"{name}: {shape.geom_type}, {shapely.get_num_coordinates(shape):,} points")
        shapes.append(shape)
    # A tiny buffer out and back closes slivers between neighboring boroughs.
    city = unary_union([s.buffer(0.00001) for s in shapes]).buffer(-0.00001)
    city = shapely.make_valid(city.simplify(SIMPLIFY_DEGREES))
    parts = list(city.geoms) if hasattr(city, "geoms") else [city]
    parts = [p for p in parts if p.geom_type == "Polygon" and p.area >= MIN_AREA_DEGREES]
    rings = [[[round(lat, 5), round(lng, 5)] for lng, lat in p.exterior.coords] for p in parts]
    holes = sum(len(p.interiors) for p in parts)
    if holes:
        print(f"Note: {holes} holes inside the outline were left out.")
    for out in OUTPUTS:
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps({
            "meta": {
                "source": "OpenStreetMap borough boundaries (water included), via OSMnx",
                "simplify_degrees": SIMPLIFY_DEGREES,
                "format": "rings: outlines as [lat, lng], outer rings only",
            },
            "rings": rings,
        }, separators=(",", ":")))
        print(f"Saved {len(rings)} outline(s), {sum(len(r) for r in rings):,} points, to {out}")


if __name__ == "__main__":
    main()
