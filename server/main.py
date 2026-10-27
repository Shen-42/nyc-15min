"""FastAPI back end for the NYC 15-Minute City Explorer.

Run from this folder with:
    uvicorn main:app --reload --port 8000
"""

import os
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from shapely.geometry import Point
from shapely.ops import unary_union

from amenities import load_amenities, reachable_amenities
from graph import WalkGraph
from grid import Grid
from hours import parse_at, status_at
from modes import NO_RAMP_PENALTY_MIN, SPEEDS, load_no_ramp_nodes, parse_mode
from rate_limit import RateLimited, RateLimiter, make_counter
from scoring import parse_weights, score_walk, settings_with_weights
from walk_area import load_land, load_parks, load_water, walking_area

GRAPH_FILE = Path(__file__).parent / "data" / "walk_graph.json"
LAND_FILE = Path(__file__).parent / "data" / "manhattan-boundary.json"
WATER_FILE = Path(__file__).parent / "data" / "water.json"
AMENITIES_FILE = Path(__file__).parent / "data" / "amenities.json"
RAMPS_FILE = Path(__file__).parent / "data" / "ramps.json"
GRID_FILE = Path(__file__).parent / "data" / "grid.json"
PARKS_FILE = Path(__file__).parent / "data" / "parks.json"

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
# Parks as (name, shape), for turning away clicks in a park: nobody lives there.
parks = []
# Groceries, pharmacies, clinics, parks, schools, and subway stations.
amenities = []
# The same places by id, for looking up opening hours.
amenity_by_id = {}
# Street corners with no curb ramp, and the extra minutes each costs in a
# wheelchair (card 11). Empty if the ramps file hasn't been built.
ramp_penalty = {}
# Every 100 m of Manhattan, scored ahead of time (card 12). None if not built.
grid = None


@asynccontextmanager
async def lifespan(app):
    global walk_graph, land, water, parks, amenities, amenity_by_id, ramp_penalty, grid
    if AMENITIES_FILE.exists():
        amenities = load_amenities(AMENITIES_FILE)
        amenity_by_id = {a["id"]: a for a in amenities}
        with_hours = sum(1 for a in amenities if a.get("hours"))
        print(f"Loaded {len(amenities):,} places ({with_hours:,} with opening hours)")
    else:
        print(f"No places file at {AMENITIES_FILE}. Run: python scripts/build_amenities.py")
    if WATER_FILE.exists():
        water = load_water(WATER_FILE)
        print(f"Loaded {len(water)} lakes and ponds")
    else:
        print(f"No water file at {WATER_FILE}. Run: python scripts/build_water.py")
    if PARKS_FILE.exists():
        parks = load_parks(PARKS_FILE)
        print(f"Loaded {len(parks)} parks")
    else:
        print(f"No parks file at {PARKS_FILE}. Run: python scripts/build_amenities.py")
    if LAND_FILE.exists():
        land = load_land(LAND_FILE)
        if water:
            land = land.difference(unary_union([shape for _, shape in water]))
    if RAMPS_FILE.exists():
        ramp_penalty = {n: NO_RAMP_PENALTY_MIN for n in load_no_ramp_nodes(RAMPS_FILE)}
        print(f"Loaded {len(ramp_penalty):,} corners with no curb ramp")
    else:
        print(f"No ramps file at {RAMPS_FILE}. Wheelchair mode will only be slower. Run: python scripts/build_ramps.py")
    if GRID_FILE.exists():
        grid = Grid.from_file(GRID_FILE)
        print(f"Loaded the Manhattan grid: {len(grid.data['cells']):,} cells, {len(grid):,} outside parks")
    else:
        print(f"No grid file at {GRID_FILE}. Run: python scripts/build_grid.py")
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
    # expose_headers lets the site read Retry-After from a 429.
    app.add_middleware(
        CORSMiddleware, allow_origins=allowed_origins, allow_methods=["GET"], expose_headers=["Retry-After"]
    )


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
# a minute per route. Normal clicking stays far below it; a script hammering
# the API gets a 429 instead of using up the server and Render's free
# bandwidth. See rate_limit.py for where the counts are kept.
SEARCHES_PER_MINUTE = 30
rate_limiter = RateLimiter(SEARCHES_PER_MINUTE, make_counter())


def check_rate_limit(key):
    try:
        rate_limiter.check(key)
    except RateLimited as limited:
        raise HTTPException(
            status_code=429,
            detail=f"Too many searches. Try again in {limited.retry_after} seconds.",
            headers={"Retry-After": str(limited.retry_after)},
        )


def plan_walk(request, kind, lat, lng, minutes, timer, mode="walk"):
    """The shared first half of every search: checks, nearest node, Dijkstra.
    mode is "walk" or "wheelchair" (card 11).

    Returns (start node, meters from the click to it, minutes left for the
    walk itself, {node: minutes}).
    """
    check_rate_limit(f"{request.client.host if request.client else 'unknown'}:{kind}")
    graph = require_graph()

    clicked = Point(lng, lat)  # shapely uses (x, y) = (lng, lat)
    for name, shape in water:
        if shape.contains(clicked):
            where = name or "the water"
            raise HTTPException(status_code=422, detail=f"That spot is in {where}. Choose a spot on land.")
    for name, shape in parks:
        if shape.contains(clicked):
            where = name or "a park"
            raise HTTPException(
                status_code=422,
                detail=f"That spot is in {where}. Choose a spot on a nearby street.",
            )

    start, gap_m = graph.nearest_node(lat, lng)
    timer.lap("nearest")

    if gap_m > MAX_START_GAP_M:
        raise HTTPException(
            status_code=422,
            detail=f"That spot is {gap_m:.0f} m from the nearest street or path. Choose a spot closer to one.",
        )

    # The click is usually a few meters from the nearest node. Count that
    # walk too, so the search gets slightly less time. Rounded so nearby
    # clicks share cached results.
    budget = round(minutes - gap_m / SPEEDS[mode], 1)

    try:
        times = cached_search(start, budget, mode)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="The 15-minute search isn't written yet (graph.py, reachable_within).")
    timer.lap("search")
    return start, gap_m, budget, times


# Recent results, kept in memory. Clicks that snap to the same street point
# (or the same spot clicked twice) are answered without redoing the work.
# 512 areas take roughly 20 MB, well inside the free plan's 512 MB.
@lru_cache(maxsize=512)
def cached_search(start, budget, mode="walk"):
    if mode == "wheelchair":
        return walk_graph.reachable_within(start, budget, SPEEDS["wheelchair"], ramp_penalty)
    return walk_graph.reachable_within(start, budget)


@lru_cache(maxsize=512)
def cached_area(start, budget, mode="walk"):
    return walking_area(walk_graph, start, cached_search(start, budget, mode), budget, SPEEDS[mode], land)


def finish(response, path, timer):
    # Shows in the terminal (and Render's logs), and in Chrome under
    # DevTools > Network > the request > Timing.
    print(f"{path} {timer.summary()}")
    response.headers["Server-Timing"] = timer.header()


Lat = Query(..., ge=40.6, le=40.95)
Lng = Query(..., ge=-74.1, le=-73.85)
Minutes = Query(15, gt=0, le=30)
# A needs profile (card 9), e.g. "grocery:3,park:3,school:0". Each weight is
# 0 (not needed) to 3 (essential); categories left out keep their defaults.
Weights = Query(None, max_length=200)
# A time to check opening hours at (card 10), New York time, e.g.
# "2026-10-26T21:00". Left out, every place counts whatever its hours.
At = Query(None, max_length=16)
# "walk" (the default) or "wheelchair" (card 11): slower, and corners
# without curb ramps cost extra minutes.
Mode = Query("walk", max_length=12)

# At most this many no-ramp corners go back to the map.
MAX_BARRIERS = 300


@app.get("/api/places")
def places(
    request: Request,
    response: Response,
    lat: float = Lat,
    lng: float = Lng,
    minutes: float = Minutes,
    weights: str | None = Weights,
    at: str | None = At,
    mode: str = Mode,
):
    """The score and the places within reach. Cheap, so the panel can fill in
    before the shaded area (the slow part) is ready."""
    try:
        settings = settings_with_weights(parse_weights(weights))
        at_time = parse_at(at) if at else None
        mode = parse_mode(mode)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
    timer = StepTimer()
    start, gap_m, budget, times = plan_walk(request, "places", lat, lng, minutes, timer, mode)
    reached = reachable_amenities(amenities, times, minutes - budget)
    if at_time:
        for place in reached:
            place["status"] = status_at(amenity_by_id[place["id"]], at_time)
        timer.lap("hours")
    score = score_walk(reached, settings)
    # How this spot compares with the rest of Manhattan (card 12). The grid
    # was scored walking at any time, so the rank is only given for those.
    if grid is not None and mode == "walk" and at_time is None and minutes == 15:
        score["rank"] = grid.rank(score["score"], settings)
    else:
        score["rank"] = None
    timer.lap("places")
    finish(response, "/api/places", timer)
    start_lat, start_lng = walk_graph.coords[start]
    return {
        "start": {"node_id": start, "lat": start_lat, "lng": start_lng, "distance_m": round(gap_m, 1)},
        "minutes": minutes,
        "at": at,
        "mode": mode,
        "amenities": reached,  # closest first; with "status" when a time was given
        "barriers": barriers_reached(times, minutes - budget) if mode == "wheelchair" else [],
        "score": score,
    }


@app.get("/api/grid")
def grid_cells(request: Request, response: Response):
    """Every 100 m of Manhattan with its score in each category, plus the
    gaps and the best spot to fill each one (card 12). The site draws the
    heat map and gap finder from this. Browsers aren't asked to keep it, so
    a rebuilt grid shows up as soon as the server restarts."""
    check_rate_limit(f"{request.client.host if request.client else 'unknown'}:grid")
    if grid is None:
        raise HTTPException(status_code=503, detail="The Manhattan grid isn't built yet. Run: python scripts/build_grid.py")
    response.headers["Cache-Control"] = "no-store"
    return grid.data


def barriers_reached(times, offset):
    """Corners with no curb ramp that the search reached, closest first."""
    reached = sorted((times[n] + offset, n) for n in ramp_penalty if n in times)
    return [
        {"lat": walk_graph.coords[n][0], "lng": walk_graph.coords[n][1], "minutes": round(t, 1)}
        for t, n in reached[:MAX_BARRIERS]
    ]


@app.get("/api/area")
def area(
    request: Request,
    response: Response,
    lat: float = Lat,
    lng: float = Lng,
    minutes: float = Minutes,
    mode: str = Mode,
):
    """The shaded walking area as a GeoJSON geometry. The slow part of a search."""
    try:
        mode = parse_mode(mode)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
    timer = StepTimer()
    start, _, budget, _ = plan_walk(request, "area", lat, lng, minutes, timer, mode)
    geometry = cached_area(start, budget, mode)
    timer.lap("area")
    finish(response, "/api/area", timer)
    return {"area": geometry}


@app.get("/api/reachable")
def reachable(
    request: Request,
    response: Response,
    lat: float = Lat,
    lng: float = Lng,
    minutes: float = Minutes,
    weights: str | None = Weights,
    at: str | None = At,
    mode: str = Mode,
):
    """Everything in one response: places, score, and area. The site uses
    /api/places and /api/area instead, so the panel doesn't wait for the area."""
    result = places(request, response, lat, lng, minutes, weights, at, mode)
    result["area"] = area(request, response, lat, lng, minutes, mode)["area"]
    return result


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
