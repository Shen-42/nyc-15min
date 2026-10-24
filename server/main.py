"""FastAPI back end for the NYC 15-Minute City Explorer.

Run from this folder with:
    uvicorn main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from shapely.geometry import Point
from shapely.ops import unary_union

from amenities import load_amenities, reachable_amenities
from graph import WALK_SPEED_M_PER_MIN, WalkGraph
from walk_area import load_land, load_water, walking_area

GRAPH_FILE = Path(__file__).parent / "data" / "walk_graph.json"
LAND_FILE = Path(__file__).parent / "data" / "manhattan-boundary.json"
WATER_FILE = Path(__file__).parent / "data" / "water.json"
AMENITIES_FILE = Path(__file__).parent / "data" / "amenities.json"

# Clicks farther than this from any street or path (the middle of a lake or a
# rail yard) are turned away instead of starting from a far-off path.
MAX_START_GAP_M = 150

# Loaded once when the server starts. None if the file hasn't been built yet.
walk_graph = None
# Manhattan's shoreline minus lakes and ponds, for trimming walking areas.
# None if the boundary file is missing.
land = None
# Lakes and ponds as (name, shape), for turning away clicks on water.
water = []
# Groceries, pharmacies, clinics, parks, schools, and subway stations.
amenities = []


@asynccontextmanager
async def lifespan(app):
    global walk_graph, land, water, amenities
    if AMENITIES_FILE.exists():
        amenities = load_amenities(AMENITIES_FILE)
        print(f"Loaded {len(amenities):,} places")
    else:
        print(f"No places file at {AMENITIES_FILE}. Run: python scripts/build_amenities.py")
    if WATER_FILE.exists():
        water = load_water(WATER_FILE)
        print(f"Loaded {len(water)} lakes and ponds")
    else:
        print(f"No water file at {WATER_FILE}. Run: python scripts/build_water.py")
    if LAND_FILE.exists():
        land = load_land(LAND_FILE)
        if water:
            land = land.difference(unary_union([shape for _, shape in water]))
    if GRAPH_FILE.exists():
        walk_graph = WalkGraph.from_file(GRAPH_FILE)
        print(f"Loaded walking graph: {len(walk_graph):,} nodes, {walk_graph.edge_count:,} edges")
    else:
        print(f"No walking graph at {GRAPH_FILE}. Run: python scripts/build_graph.py")
    yield


app = FastAPI(title="NYC 15-Minute City Explorer API", version="0.1.0", lifespan=lifespan)


def require_graph():
    if walk_graph is None:
        raise HTTPException(
            status_code=503,
            detail="Walking graph not built yet. Run: python scripts/build_graph.py",
        )
    return walk_graph


@app.get("/api/health")
def health():
    """Lets the front end check that the server is up."""
    return {"status": "ok", "version": app.version, "graph_loaded": walk_graph is not None}


@app.get("/api/graph/info")
def graph_info():
    graph = require_graph()
    return {
        "nodes": len(graph),
        "edges": graph.edge_count,
        "source": graph.meta.get("source"),
        "built": graph.meta.get("built"),
    }


@app.get("/api/nearest-node")
def nearest_node(
    lat: float = Query(..., ge=40.6, le=40.95),
    lng: float = Query(..., ge=-74.1, le=-73.85),
):
    """The graph node closest to a clicked point. Card 4 starts its search here."""
    graph = require_graph()
    node_id, dist = graph.nearest_node(lat, lng)
    node_lat, node_lng = graph.coords[node_id]
    return {"node_id": node_id, "lat": node_lat, "lng": node_lng, "distance_m": round(dist, 1)}


@app.get("/api/reachable")
def reachable(
    lat: float = Query(..., ge=40.6, le=40.95),
    lng: float = Query(..., ge=-74.1, le=-73.85),
    minutes: float = Query(15, gt=0, le=30),
):
    """Every graph node you can walk to from a clicked point within `minutes`."""
    graph = require_graph()

    clicked = Point(lng, lat)  # shapely uses (x, y) = (lng, lat)
    for name, shape in water:
        if shape.contains(clicked):
            where = name or "the water"
            raise HTTPException(status_code=422, detail=f"That spot is in {where}. Try clicking on land.")

    start, gap_m = graph.nearest_node(lat, lng)

    if gap_m > MAX_START_GAP_M:
        raise HTTPException(
            status_code=422,
            detail=f"That spot is {gap_m:.0f} m from the nearest street or path. Try clicking closer to one.",
        )

    # The click is usually a few meters from the nearest node. Count that
    # walk too, so the search gets slightly less time.
    budget = minutes - gap_m / WALK_SPEED_M_PER_MIN

    try:
        times = graph.reachable_within(start, budget)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="The 15-minute search isn't written yet (graph.py, reachable_within).")

    offset = minutes - budget
    points = [
        [*graph.coords[node], round(t + offset, 2)]
        for node, t in times.items()
    ]
    start_lat, start_lng = graph.coords[start]
    return {
        "start": {"node_id": start, "lat": start_lat, "lng": start_lng, "distance_m": round(gap_m, 1)},
        "minutes": minutes,
        "points": points,  # [lat, lng, minutes to walk there]
        "area": walking_area(graph, start, times, budget, WALK_SPEED_M_PER_MIN, land),  # GeoJSON geometry
        "amenities": reachable_amenities(amenities, times, offset),  # closest first
    }
