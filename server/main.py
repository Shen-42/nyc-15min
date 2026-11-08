"""FastAPI back end for the NYC 15-Minute City Explorer.

Run from this folder with:
    uvicorn main:app --reload --port 8000
"""

import logging
import os
import resource
import sys
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import shapely
from shapely.geometry import Point
from shapely.ops import unary_union

import accounts
from amenities import PlaceIndex, load_amenities, reachable_amenities
from graph import WalkGraph
from grid import Grid
from hours import parse_at, status_at
from modes import NO_RAMP_PENALTY_MIN, SPEEDS, load_no_ramp_nodes, parse_mode
from rate_limit import RateLimited, RateLimiter, make_counter
from scoring import parse_weights, score_walk, settings_with_weights
from shared_cache import make_shared_cache
from usage import make_usage
from walk_area import NearestName, Outlines, big_land, empty_islands, in_open_ocean, load_waterways, water_phrase, load_boroughs, load_not_lived_on, load_parks, load_water, walking_area

GRAPH_FILE = Path(__file__).parent / "data" / "walk_graph.npz"
WATER_FILE = Path(__file__).parent / "data" / "water.json"
# Named rivers, bays, and straits, to say which one a click landed in
# (build_water.py). Without it, clicks in them are still turned away.
WATERWAYS_FILE = Path(__file__).parent / "data" / "waterways.json"
AMENITIES_FILE = Path(__file__).parent / "data" / "amenities.json"
RAMPS_FILE = Path(__file__).parent / "data" / "ramps.json"
DATA_DIR = Path(__file__).parent / "data"
PARKS_FILE = Path(__file__).parent / "data" / "parks.json"

# Clicks farther than this from any street or path (the middle of a lake or a
# rail yard) are turned away instead of starting from a far-off path.
MAX_START_GAP_M = 150

# Loaded once when the server starts. None if the file hasn't been built yet.
walk_graph = None
# Each borough's land, to say which one a spot is in (card 15).
boroughs = Outlines([])
# Islands where nobody lives, such as Rikers and Randall's (card 15).
islands = Outlines([])
# The rivers and bays by name (card 15).
waterways = Outlines([])
# The rivers by center line and the bays by label point, for water with no outline.
water_labels = NearestName([])
# Islands with almost no paths, found from the graph when it loads.
empty_land = Outlines([])
# The five boroughs' shoreline minus lakes and ponds, for trimming walking areas.
land = None
# Lakes and ponds, for turning away clicks on water.
water = Outlines([])
# Parks, for turning away clicks in a park: nobody lives there.
parks = Outlines([])
# Groceries, pharmacies, clinics, parks, schools, and subway stations.
amenities = []
# The same places, indexed for matching against a walk (amenities.py).
places_index = PlaceIndex([])
# The same places by id, for looking up opening hours.
amenity_by_id = {}
# Street corners with no curb ramp, and the extra minutes each costs in a
# wheelchair (card 11). Empty if the ramps file hasn't been built.
ramp_penalty = {}
# Every 100 m of the city, scored ahead of time (cards 12 and 15). None if not built.
grid = None
# Walking areas saved in Redis, so they outlive the API sleeping (card 15).
# None without REDIS_URL.
shared_cache = None

# Part of every shared-cache key. Bump it when walk_area.py changes how
# areas are drawn, so areas drawn the old way aren't served.
AREA_FORMAT = 2  # 2: drawn on a grid of squares (card 15)


def peak_memory_mb():
    """The most memory this process has used so far, in MB."""
    if sys.platform.startswith("linux"):
        with open("/proc/self/status") as status:
            for line in status:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1000  # KB
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6  # macOS: bytes


@asynccontextmanager
async def lifespan(app):
    global walk_graph, boroughs, islands, empty_land, waterways, water_labels, land, water, parks, amenities, places_index, amenity_by_id, ramp_penalty, grid, shared_cache
    if AMENITIES_FILE.exists():
        amenities = load_amenities(AMENITIES_FILE)
        places_index = PlaceIndex(amenities)
        for place in amenities:
            del place["nodes"]  # now in the index's arrays; no need to hold them twice
        amenity_by_id = {a["id"]: a for a in amenities}
        with_hours = sum(1 for a in amenities if a.get("hours"))
        print(f"Loaded {len(amenities):,} places ({with_hours:,} with opening hours)")
    else:
        print(f"No places file at {AMENITIES_FILE}. Run: python scripts/build_amenities.py")
    if WATER_FILE.exists():
        water = Outlines(load_water(WATER_FILE))
        print(f"Loaded {len(water)} lakes and ponds")
    else:
        print(f"No water file at {WATER_FILE}. Run: python scripts/build_water.py")
    if WATERWAYS_FILE.exists():
        named = load_waterways(WATERWAYS_FILE)
        areas = ("Polygon", "MultiPolygon")
        waterways = Outlines([(n, s) for n, s, _ in named if s.geom_type in areas])
        water_labels = NearestName([item for item in named if item[1].geom_type not in areas], land=big_land())
        print(f"Loaded {len(waterways)} named water areas and {len(water_labels)} river lines and bay labels")
    if PARKS_FILE.exists():
        parks = Outlines(load_parks(PARKS_FILE))
        print(f"Loaded {len(parks)} parks")
    else:
        print(f"No parks file at {PARKS_FILE}. Run: python scripts/build_amenities.py")
    islands = Outlines(load_not_lived_on())
    by_name = load_boroughs()
    boroughs = Outlines(list(by_name.items()))
    land = shapely.make_valid(unary_union(list(by_name.values())))
    if len(water):
        land = land.difference(unary_union([shape for _, shape in water]))
    if RAMPS_FILE.exists():
        ramp_penalty = {n: NO_RAMP_PENALTY_MIN for n in load_no_ramp_nodes(RAMPS_FILE)}
        print(f"Loaded {len(ramp_penalty):,} corners with no curb ramp")
    else:
        print(f"No ramps file at {RAMPS_FILE}. Wheelchair mode will only be slower. Run: python scripts/build_ramps.py")
    grid = Grid.from_dir(DATA_DIR)
    if grid is not None:
        print(f"Loaded the grid: {len(grid):,} squares outside parks in {', '.join(grid.boroughs)}")
    else:
        print(f"No grid files in {DATA_DIR}. Run: python scripts/build_grid.py")
    if GRAPH_FILE.exists():
        walk_graph = WalkGraph.from_file(GRAPH_FILE)
        print(f"Loaded walking graph: {len(walk_graph):,} nodes, {walk_graph.edge_count:,} edges")
        empty_land = Outlines(empty_islands(walk_graph.lat, walk_graph.lng))
        print(f"Found {len(empty_land)} islands with no streets")
        version = f"{AREA_FORMAT}-{walk_graph.meta.get('built')}-{len(walk_graph)}"
        shared_cache = make_shared_cache(redis_client, version)
    else:
        print(f"No walking graph at {GRAPH_FILE}. Run: python scripts/build_graph.py")
    accounts.setup(usage, check_rate_limit)
    # Render's free plan stops the API if it goes over 512 MB.
    print(f"Memory used while starting: {peak_memory_mb():.0f} MB at most (Render's free plan has 512 MB)")
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

# Unexpected errors (card 14). Any exception a route doesn't handle is caught
# here, logged with the request that caused it, and answered with a plain
# message and a short request id, instead of a bare "Internal Server Error".
# The id is also in the X-Request-ID header of every response, so a
# visitor's report can be matched to the log line.
# This is registered before the CORS middleware, so it sits inside it: a
# crash still gets CORS headers, and the browser can read the message
# instead of reporting a cross-origin error.
log = logging.getLogger("nyc15min")
UNEXPECTED_ERROR = "Something went wrong on our side. Try again in a minute."


@app.middleware("http")
async def catch_unexpected_errors(request, call_next):
    request_id = uuid.uuid4().hex[:8]
    try:
        response = await call_next(request)
    except Exception:
        log.error(
            "Unexpected error %s on %s %s?%s\n%s",
            request_id,
            request.method,
            request.url.path,
            request.url.query,
            traceback.format_exc(),
        )
        response = JSONResponse(status_code=500, content={"detail": UNEXPECTED_ERROR, "request_id": request_id})
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def readable_validation_error(request, err):
    """FastAPI's own input checks (a missing lat, a word where a number
    belongs) answer with a list of objects, which a page can't show as is.
    Answer with one sentence instead, keeping the list for programs."""
    errors = err.errors()
    first = errors[0] if errors else {}
    field = next((str(part) for part in reversed(first.get("loc", [])) if not isinstance(part, int)), "input")
    message = first.get("msg", "is not valid").rstrip(".")
    detail = f"Invalid {field}: {message[0].lower() + message[1:] if message else 'not valid'}."
    return JSONResponse(status_code=422, content={"detail": detail, "errors": jsonable(errors)})


def jsonable(errors):
    """Validation errors can hold exception objects; keep only plain fields."""
    return [{k: e.get(k) for k in ("loc", "msg", "type")} for e in errors]


# Security headers on every API response. The API only returns JSON, so it
# may not be framed or treated as a page, and browsers shouldn't guess types.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000",
}
# Not on /docs, the interactive docs page used locally, which needs scripts.
API_CSP = "default-src 'none'; frame-ancestors 'none'"


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if not request.url.path.startswith(("/docs", "/redoc")):
        response.headers.setdefault("Content-Security-Policy", API_CSP)
    return response

# On Render the site and the API have different addresses, so the browser
# needs permission to call the API from the site. ALLOWED_ORIGINS lists the
# site's address (comma-separated if more than one). Locally, Vite forwards
# /api to this server, so no permission is needed there.
allowed_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if allowed_origins:
    # expose_headers lets the site read Retry-After from a 429. Accounts
    # (card 13) add saves and deletes, sent with a sign-in token.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Retry-After", "X-Suggest"],
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
    lat: float = Query(..., ge=40.47, le=40.93),
    lng: float = Query(..., ge=-74.27, le=-73.68),
):
    """The graph node closest to a clicked point. Card 4 starts its search here."""
    graph = require_graph()
    node_id, dist = graph.nearest_node(lat, lng)
    node_lat, node_lng = graph.coords[node_id]
    return {"node_id": node_id, "lat": node_lat, "lng": node_lng, "distance_m": round(dist, 1)}


# Sent with a turned-away click (water, a park, far from any street) so the
# site can offer "Use the nearest street", which asks /api/nearest-street.
# Not sent for islands where nobody lives: their nearest street is on the island.
SUGGEST_STREET = {"X-Suggest": "nearest-street"}
# How many nearby graph nodes /api/nearest-street looks through: about 1.3 km
# around a click in Central Park, enough to reach a street outside it.
NEARBY_CANDIDATES = 2000


@app.get("/api/nearest-street")
def nearest_street(
    lat: float = Query(..., ge=40.47, le=40.93),
    lng: float = Query(..., ge=-74.27, le=-73.68),
):
    """The nearest point on a street a search would accept: on land, and not
    in a park, a lake, or on an island where nobody lives. For the site's
    "Use the nearest street" after a click is turned away."""
    graph = require_graph()
    for node_id, node_lat, node_lng, dist in graph.nearby_nodes(lat, lng, NEARBY_CANDIDATES):
        spot = Point(node_lng, node_lat)
        if len(boroughs) and not boroughs.find(spot)[0]:
            continue  # on a bridge or pier over the water
        if any(outlines.find(spot)[0] for outlines in (islands, empty_land, water, parks)):
            continue
        return {"lat": node_lat, "lng": node_lng, "distance_m": round(dist)}
    raise HTTPException(status_code=404, detail="No street nearby. Pick a spot on the map.")


# Rate limit: each visitor (by IP address) gets SEARCHES_PER_MINUTE searches
# a minute per route. Normal clicking stays far below it; a script hammering
# the API gets a 429 instead of using up the server and Render's free
# bandwidth. See rate_limit.py for where the counts are kept.
SEARCHES_PER_MINUTE = 30


def connect_redis():
    """A Redis client if REDIS_URL is set (on Render: the free Key Value
    instance in render.yaml), otherwise None (local development, tests).
    Shared by the rate limit, the usage counts, and the area cache."""
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    import redis

    return redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)


redis_client = connect_redis()
rate_limiter = RateLimiter(SEARCHES_PER_MINUTE, make_counter(redis_client))
# Requests per route per day, for the admin page (card 13).
usage = make_usage(redis_client)


def client_ip(request):
    """The visitor's real address, for the rate limit.

    On Render a request passes through Cloudflare, then Render's load
    balancer, and each adds to the X-Forwarded-For list:
        [anything the visitor sent..., visitor, Cloudflare, Render]
    (measured October 2026). Entries a visitor sends themselves come first
    and can be made up, so the address is counted from the end, where only
    Cloudflare and Render write. Locally there's no such header, and the
    connection's own address is used.
    """
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    if len(hops) >= 3:
        return hops[-3]
    return request.client.host if request.client else "unknown"


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
    check_rate_limit(f"{client_ip(request)}:{kind}")
    graph = require_graph()

    clicked = Point(lng, lat)  # shapely uses (x, y) = (lng, lat)
    on_island, name = islands.find(clicked)
    if on_island:
        raise HTTPException(status_code=422, detail=f"{name} has no residential areas. Pick a spot where people live.")
    on_empty_island, _ = empty_land.find(clicked)
    if on_empty_island:
        raise HTTPException(status_code=422, detail="This island has no residential areas. Pick a spot where people live.")
    in_water, name = water.find(clicked)
    if in_water:
        raise HTTPException(
            status_code=422, detail=f"That's in {water_phrase(name, lat, lng) if name else 'the water'}. Pick a spot on land.", headers=SUGGEST_STREET
        )
    # Rivers, bays, and the ocean: off the shoreline but inside the city's
    # limits, which run through the water. The site sends these clicks so
    # the server can name the water.
    if len(boroughs) and not boroughs.find(clicked)[0]:
        _, name = waterways.find(clicked)
        # Open ocean is the Atlantic, even within reach of Jamaica Bay's label.
        if not name and not in_open_ocean(lat, lng):
            name = water_labels.find(clicked)
        raise HTTPException(
            status_code=422,
            detail=f"That's in {water_phrase(name, lat, lng)}. Pick a spot on land.",
            headers=SUGGEST_STREET,
        )
    in_park, name = parks.find(clicked)
    if in_park:
        raise HTTPException(
            status_code=422,
            detail=f"That's in {name or 'a park'}. Pick a spot on a nearby street.",
            headers=SUGGEST_STREET,
        )

    start, gap_m = graph.nearest_node(lat, lng)
    timer.lap("nearest")

    if gap_m > MAX_START_GAP_M:
        raise HTTPException(
            status_code=422,
            detail=f"That's {gap_m:.0f} m from the nearest street. Pick a spot closer to one.",
            headers=SUGGEST_STREET,
        )

    # The click is usually a few meters from the nearest node. Count that
    # walk too, so the search gets slightly less time. Rounded so nearby
    # clicks share cached results.
    budget = round(minutes - gap_m / SPEEDS[mode], 1)

    times = cached_search(start, budget, mode)
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
    # Then Redis, which keeps areas while the API sleeps (shared_cache.py).
    key = f"{mode}:{budget}:{start}"
    if shared_cache is not None:
        saved = shared_cache.get(key)
        if saved is not None:
            return saved
    geometry = walking_area(walk_graph, start, cached_search(start, budget, mode), budget, SPEEDS[mode], land)
    if shared_cache is not None:
        shared_cache.set(key, geometry)
    return geometry


def finish(response, path, timer):
    # Shows in the terminal (and Render's logs), and in Chrome under
    # DevTools > Network > the request > Timing.
    print(f"{path} {timer.summary()}")
    usage.hit(path)
    response.headers["Server-Timing"] = timer.header()


# A box around the five boroughs (card 15).
Lat = Query(..., ge=40.47, le=40.93)
Lng = Query(..., ge=-74.27, le=-73.68)
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
    reached = reachable_amenities(places_index, times, minutes - budget)
    if at_time:
        for place in reached:
            place["status"] = status_at(amenity_by_id[place["id"]], at_time)
        timer.lap("hours")
    score = score_walk(reached, settings)
    _, borough = boroughs.find(Point(lng, lat))  # None just off the shore
    # How this spot compares with its borough and the city (cards 12 and 15).
    # The grid was scored walking at any time, so the rank is only given for those.
    if grid is not None and mode == "walk" and at_time is None and minutes == 15:
        score["rank"] = grid.rank(score["score"], settings, borough)
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
        "borough": borough,
        "amenities": reached,  # closest first; with "status" when a time was given
        "barriers": barriers_reached(times, minutes - budget) if mode == "wheelchair" else [],
        "score": score,
    }


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
    hits_before = shared_cache.hits if shared_cache else 0
    geometry = cached_area(start, budget, mode)
    # Named so the log shows when an area came from Redis instead of being drawn.
    timer.lap("area-from-redis" if shared_cache and shared_cache.hits > hits_before else "area")
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


# Accounts, saved places, needs profiles, and admin routes (card 13).
app.include_router(accounts.router)
