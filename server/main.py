"""FastAPI back end for the NYC 15-Minute City Explorer.

Run from this folder with:
    uvicorn main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from graph import WalkGraph

GRAPH_FILE = Path(__file__).parent / "data" / "walk_graph.json"

# Loaded once when the server starts. None if the file hasn't been built yet.
walk_graph = None


@asynccontextmanager
async def lifespan(app):
    global walk_graph
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


# Card 4 adds the 15-minute search, for example:
# @app.get("/api/reachable")
# def reachable(lat: float, lng: float, minutes: int = 15): ...
