"""FastAPI back end for the NYC 15-Minute City Explorer.

Run from this folder with:
    uvicorn main:app --reload --port 8000
"""

import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from shapely.geometry import Point
from shapely.ops import unary_union

from amenities import load_amenities, reachable_amenities
from graph import WALK_SPEED_M_PER_MIN, WalkGraph
from scoring import score_walk
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


# Render sets RENDER=true on its servers. There, the interactive API docs
# at /docs are turned off: nobody needs them, and they map out the API.
ON_RENDER = os.environ.get("RENDER") == "true"

app = FastAPI(
    title="NYC 15-Minute City Explorer API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if ON_RENDER else "/docs",
    redoc_url=None if ON_RENDER else "/redoc",
    openapi_url=None if ON_RENDER else "/openapi.json",
)

# Compress responses over 1 KB. A search result shrinks to about a quarter.
app.add_middleware(GZipMiddleware, minimum_size=1000)

# On Render the site and the API have different addresses, so the browser
# needs permission to call the API from the site. ALLOWED_ORIGINS lists the
# site's address (comma-separated if more than one). Locally, Vite forwards
# /api to this server, so no permission is needed there.
allowed_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if allowed_origins:
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_methods=["GET"])


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


# Rate limit: each visitor (by IP address) gets SEARCHES_PER_MINUTE searches
# a minute. Normal clicking stays far below it; a script hammering the API
# gets a 429 instead of using up the server and Render's free bandwidth.
SEARCHES_PER_MINUTE = 30
recent_searches = defaultdict(deque)  # IP -> times of its recent searches


def check_rate_limit(ip):
    now = time.monotonic()
    times = recent_searches[ip]
    while times and now - times[0] > 60:
        times.popleft()
    if len(times) >= SEARCHES_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Too many searches in a minute. Wait a moment and try again.")
    times.append(now)
    # Forget visitors who have gone quiet, so the table doesn't grow forever.
    if len(recent_searches) > 10_000:
        for old_ip in [k for k, v in recent_searches.items() if not v or now - v[-1] > 60]:
            del recent_searches[old_ip]


@app.get("/api/reachable")
def reachable(
    request: Request,
    response: Response,
    lat: float = Query(..., ge=40.6, le=40.95),
    lng: float = Query(..., ge=-74.1, le=-73.85),
    minutes: float = Query(15, gt=0, le=30),
):
    """Every graph node you can walk to from a clicked point within `minutes`."""
    check_rate_limit(request.client.host if request.client else "unknown")
    graph = require_graph()
    timer = StepTimer()

    clicked = Point(lng, lat)  # shapely uses (x, y) = (lng, lat)
    for name, shape in water:
        if shape.contains(clicked):
            where = name or "the water"
            raise HTTPException(status_code=422, detail=f"That spot is in {where}. Try clicking on land.")

    start, gap_m = graph.nearest_node(lat, lng)
    timer.lap("nearest")

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
    timer.lap("search")

    offset = minutes - budget
    start_lat, start_lng = graph.coords[start]
    area = walking_area(graph, start, times, budget, WALK_SPEED_M_PER_MIN, land)
    timer.lap("area")
    reached = reachable_amenities(amenities, times, offset)
    score = score_walk(reached)
    timer.lap("places")

    # Shows in the terminal, and in Chrome under DevTools > Network > the
    # request > Timing, so slow steps are easy to spot.
    print(f"/api/reachable {timer.summary()}")
    response.headers["Server-Timing"] = timer.header()
    return {
        "start": {"node_id": start, "lat": start_lat, "lng": start_lng, "distance_m": round(gap_m, 1)},
        "minutes": minutes,
        "area": area,  # GeoJSON geometry
        "amenities": reached,  # closest first
        "score": score,
    }


class StepTimer:
    """Measures how long each step of a request takes, in milliseconds."""

    def __init__(self):
        self.last = time.perf_counter()
        self.steps = []

    def lap(self, name):
        now = time.perf_counter()
        self.steps.append((name, (now - self.last) * 1000))
        self.last = now

    def summary(self):
        total = sum(ms for _, ms in self.steps)
        return ", ".join(f"{name} {ms:.0f} ms" for name, ms in self.steps) + f" (total {total:.0f} ms)"

    def header(self):
        return ", ".join(f"{name};dur={ms:.1f}" for name, ms in self.steps)
