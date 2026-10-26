"""Download NYC's curb ramps and find street corners without one (card 11).

Run from the server folder, with the virtual environment active, after
scripts/build_graph.py (it needs the graph's list of street corners):
    python scripts/build_ramps.py

Source: NYC DOT's "Pedestrian Ramp Locations" on NYC Open Data (ufzp-rrqu),
a point for every curb ramp in the city. A street corner with no ramp
within RAMP_RADIUS_M is marked as having none.

It writes data/ramps.json.
"""

import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from shapely import STRtree
from shapely.geometry import Point

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))
from walk_area import load_land  # noqa: E402

GRAPH_FILE = SERVER_DIR / "data" / "walk_graph.json"
LAND_FILE = SERVER_DIR / "data" / "manhattan-boundary.json"
OUTPUT_FILE = SERVER_DIR / "data" / "ramps.json"

SITE = "https://data.cityofnewyork.us"
DATASET = "ufzp-rrqu"
PAGE_SIZE = 50_000

# A street corner counts as having a ramp if one is within this distance of
# the graph node. Graph nodes sit in the middle of an intersection, and on an
# avenue the curb corners are 15 to 25 m from there.
RAMP_RADIUS_M = 30

# Work in meters around Manhattan's middle (the same projection as build_amenities.py).
LAT0, LNG0 = 40.78, -73.97
M_PER_DEG_LAT = 110_540
M_PER_DEG_LNG = 111_320 * math.cos(math.radians(LAT0))


def to_meters(lat, lng):
    return Point((lng - LNG0) * M_PER_DEG_LNG, (lat - LAT0) * M_PER_DEG_LAT)


def get_json(url, tries=5):
    """GET a JSON URL, waiting longer after each failure (5, 10, 20, 40 s)."""
    request = urllib.request.Request(url, headers={"User-Agent": "nyc-15min (github.com/Shen-42/nyc-15min)"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError) as err:
            if attempt == tries - 1:
                raise
            wait = 5 * 2**attempt
            print(f"  {err}. Trying again in {wait} s")
            time.sleep(wait)


def point_column():
    """The dataset's location column. Found from its metadata, so a renamed column doesn't break this."""
    meta = get_json(f"{SITE}/api/views/{DATASET}.json")
    columns = [(c["fieldName"], c["dataTypeName"]) for c in meta["columns"]]
    print("Columns: " + ", ".join(f"{name} ({kind})" for name, kind in columns))
    for name, kind in columns:
        if kind in ("point", "multipoint", "location"):
            return name, meta.get("rowsUpdatedAt")
    sys.exit(f"No location column in {DATASET}. The columns are listed above.")


def lat_lng(value):
    """A Socrata point ({"type": "Point", "coordinates": [lng, lat]}) or location value."""
    if not value:
        return None
    if "coordinates" in value:
        coords = value["coordinates"]
        if value.get("type") == "MultiPoint":
            coords = coords[0]
        return float(coords[1]), float(coords[0])
    if "latitude" in value:
        return float(value["latitude"]), float(value["longitude"])
    return None


def download_ramps(column, land):
    west, south, east, north = land.bounds
    where = f"within_box({column}, {north}, {west}, {south}, {east})"
    ramps = []
    offset = 0
    while True:
        query = urllib.parse.urlencode({
            "$select": column,
            "$where": where,
            "$order": ":id",
            "$limit": PAGE_SIZE,
            "$offset": offset,
        })
        rows = get_json(f"{SITE}/resource/{DATASET}.json?{query}")
        for row in rows:
            point = lat_lng(row.get(column))
            if point and land.contains(Point(point[1], point[0])):
                ramps.append(point)
        print(f"  {offset + len(rows):,} rows read, {len(ramps):,} ramps in Manhattan so far")
        if len(rows) < PAGE_SIZE:
            return ramps
        offset += PAGE_SIZE


def main():
    graph = json.loads(GRAPH_FILE.read_text())
    curbs = graph.get("curb_nodes")
    if not curbs:
        sys.exit("The graph has no street corners yet. Run python scripts/build_graph.py first.")
    coords = {node_id: (lat, lng) for node_id, lat, lng in graph["nodes"]}

    land = load_land(LAND_FILE)
    column, updated = point_column()
    print(f"Downloading curb ramps from NYC Open Data ({DATASET})...")
    ramps = download_ramps(column, land)
    if not ramps:
        sys.exit("No ramps came back. Not saving.")

    tree = STRtree([to_meters(lat, lng) for lat, lng in ramps])
    no_ramp = []
    for node_id in curbs:
        lat, lng = coords[node_id]
        if not len(tree.query(to_meters(lat, lng), predicate="dwithin", distance=RAMP_RADIUS_M)):
            no_ramp.append(node_id)

    share = len(no_ramp) / len(curbs)
    OUTPUT_FILE.write_text(json.dumps({
        "meta": {
            "source": f"NYC DOT Pedestrian Ramp Locations, NYC Open Data ({DATASET})",
            "dataset_updated": updated,
            "built": date.today().isoformat(),
            "ramps": len(ramps),
            "curb_nodes": len(curbs),
            "ramp_radius_m": RAMP_RADIUS_M,
        },
        "no_ramp_nodes": no_ramp,
    }, separators=(",", ":")))
    print(f"\nSaved to {OUTPUT_FILE}")
    print(f"  ramps in Manhattan        {len(ramps):,}")
    print(f"  street corners checked    {len(curbs):,}")
    print(f"  corners with no ramp      {len(no_ramp):,} ({share:.0%})")
    if share > 0.3:
        print("  That's a lot. Check RAMP_RADIUS_M and the dataset before relying on it.")


if __name__ == "__main__":
    main()
