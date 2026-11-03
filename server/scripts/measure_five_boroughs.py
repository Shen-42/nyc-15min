"""Measure what a five-borough walking graph would cost the server (card 15, task 1).

Downloads the walking network for all five boroughs, saves it in the same
JSON format as data/walk_graph.json and in a compact NumPy format, and
prints how big each one is, how much memory it takes once loaded, how long
it takes to load, and how fast a 15-minute search runs on it.

Nothing here changes the live data. Output goes to cache/, which git ignores.

Run from the server folder, with the virtual environment active:
    pip install -r requirements-build.txt scipy
    python scripts/measure_five_boroughs.py

To measure a graph you already have (for example Manhattan's, to compare):
    python scripts/measure_five_boroughs.py --graph data/walk_graph.json
"""

import argparse
import json
import random
import resource
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))  # so `import graph` finds server/graph.py

CACHE_DIR = SERVER_DIR / "cache"
NYC_JSON = CACHE_DIR / "nyc_walk_graph.json"

# Names as Nominatim knows them. Each one is checked by printing its area.
BOROUGHS = [
    "Manhattan, New York, USA",
    "Brooklyn, New York, USA",
    "Queens, New York, USA",
    "The Bronx, New York, USA",
    "Staten Island, New York, USA",
]
MIN_COMPONENT_NODES = 50  # same as build_graph.py
WALK_M_PER_MIN = 80
MINUTES = 15
SAMPLE_STARTS = 30


# ---------- download ----------

def share_cache_across_servers(servers):
    """OSMnx names each cached response after the full request address,
    server included, so a piece saved from one server is downloaded again
    when the next try goes to another. Look for it under every server's name."""
    import osmnx as ox
    from osmnx import _http

    check = _http._check_cache

    def check_every_server(key):
        current = ox.settings.overpass_url.rstrip("/")
        if key.startswith(current + "/"):
            for server in servers:
                found = check(server.rstrip("/") + key[len(current):])
                if found is not None:
                    return found
        return check(key)

    _http._check_cache = check_every_server


def download():
    import numpy as np
    import osmnx as ox
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    sys.path.insert(0, str(SERVER_DIR / "scripts"))
    import overpass

    overpass.configure()
    # Each try re-requests only the pieces not yet cached, so tries are cheap.
    # Busy public servers fail often, so allow more of them than the default 6.
    overpass.RETRIES = 20
    share_cache_across_servers(overpass.servers())
    # Ask for each borough in pieces of at most 50 km² (OSMnx's default is
    # 2,500 km², so a whole borough goes in one request). Big requests time
    # out on busy servers; small ones finish.
    ox.settings.max_query_area_size = 50_000_000
    coords = {}  # node id -> (lat, lng); nodes on a borough line appear once
    best = {}  # (smaller id, larger id) -> (length, u, v, curve points); shortest kept, as in build_graph.py
    for place in BOROUGHS:
        area = ox.geocode_to_gdf(place)
        km2 = area.to_crs(epsg=32618).area.iloc[0] / 1e6
        print(f"\n{place}: boundary covers {km2:,.0f} km² (land and water)")
        start = time.time()
        G = overpass.download(place, lambda: ox.graph_from_polygon(
            area.geometry.iloc[0], network_type="walk", retain_all=True, truncate_by_edge=True))
        print(f"{place}: {len(G.nodes):,} nodes, {len(G.edges):,} edges in {time.time() - start:.0f} s")
        for n, d in G.nodes(data=True):
            coords[int(n)] = (round(d["y"], 6), round(d["x"], 6))
        for u, v, d in G.edges(data=True):
            if u == v:
                continue
            key = (min(u, v), max(u, v))
            if key not in best or d["length"] < best[key][0]:
                geom = d.get("geometry")
                between = [[round(y, 6), round(x, 6)] for x, y in geom.coords[1:-1]] if geom is not None else []
                best[key] = (d["length"], int(u), int(v), between)
        del G  # keep only one borough's OSMnx graph in memory at a time

    # Drop small disconnected pieces, as build_graph.py does. Bridges join the
    # boroughs, so this runs on the whole city at once.
    ids = list(coords)
    index = {n: i for i, n in enumerate(ids)}
    a = np.array([index[k[0]] for k in best], dtype=np.int32)
    b = np.array([index[k[1]] for k in best], dtype=np.int32)
    links = coo_matrix((np.ones(len(a), dtype=np.int8), (a, b)), shape=(len(ids), len(ids)))
    _, label = connected_components(links, directed=False)
    big = np.bincount(label)[label] >= MIN_COMPONENT_NODES
    keep = {ids[i] for i in np.flatnonzero(big)}
    print(f"\nDropped {len(ids) - len(keep):,} nodes in small disconnected pieces")

    nodes = [[n, *coords[n]] for n in ids if n in keep]
    edges = []
    for length, u, v, between in best.values():
        if u in keep:
            edge = [u, v, round(length, 1)]
            if between:
                edge.append(between)
            edges.append(edge)

    CACHE_DIR.mkdir(exist_ok=True)
    NYC_JSON.write_text(json.dumps({"nodes": nodes, "edges": edges}, separators=(",", ":")))
    print(f"Saved {len(nodes):,} nodes and {len(edges):,} edges to {NYC_JSON}")
    return NYC_JSON


# ---------- the compact format ----------

def to_arrays(json_path, npz_path):
    """Write the graph as flat NumPy arrays: coordinates, a CSR adjacency
    list (both directions), and the curve points of each edge."""
    import numpy as np

    data = json.loads(Path(json_path).read_text())
    ids = np.array([n[0] for n in data["nodes"]], dtype=np.int64)
    index = {node_id: i for i, node_id in enumerate(ids.tolist())}
    lat = np.array([n[1] for n in data["nodes"]], dtype=np.float64)
    lng = np.array([n[2] for n in data["nodes"]], dtype=np.float64)

    a = np.array([index[e[0]] for e in data["edges"]], dtype=np.int32)
    b = np.array([index[e[1]] for e in data["edges"]], dtype=np.int32)
    # 64-bit: scipy's dijkstra copies the whole edge list to 64-bit on every
    # call if given 32-bit lengths, which made each search about 10x slower.
    length = np.array([e[2] for e in data["edges"]], dtype=np.float64)
    # Curve points for drawing, flattened: edge k's points are
    # shape_points[shape_start[k]:shape_start[k + 1]].
    counts = np.array([len(e[3]) if len(e) > 3 else 0 for e in data["edges"]], dtype=np.int32)
    shape_start = np.concatenate([[0], np.cumsum(counts)]).astype(np.int32)
    shape_points = np.array([p for e in data["edges"] if len(e) > 3 for p in e[3]],
                            dtype=np.float32).reshape(-1, 2)

    # CSR: row i's neighbors are col[indptr[i]:indptr[i + 1]].
    src = np.concatenate([a, b])
    dst = np.concatenate([b, a])
    w = np.concatenate([length, length])
    order = np.argsort(src, kind="stable")
    indptr = np.concatenate([[0], np.cumsum(np.bincount(src, minlength=len(ids)))]).astype(np.int32)
    np.savez(npz_path, ids=ids, lat=lat, lng=lng, indptr=indptr, col=dst[order], weight=w[order],
             edge_a=a, edge_b=b, shape_start=shape_start, shape_points=shape_points)


def load_arrays(npz_path):
    import numpy as np
    from scipy.sparse import csr_matrix

    d = np.load(npz_path)
    n = len(d["ids"])
    matrix = csr_matrix((d["weight"], d["col"], d["indptr"]), shape=(n, n))
    return matrix, {k: d[k] for k in d.files}


# ---------- measuring (each load runs in its own process for clean numbers) ----------

def peak_rss_mb():
    """Most memory this process has used, in MB."""
    if sys.platform.startswith("linux"):
        # Linux's ru_maxrss carries over the parent's peak when the parent was
        # bigger, which hid the real figure. VmHWM starts fresh in each program.
        with open("/proc/self/status") as status:
            for line in status:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1e3  # KB
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6  # macOS: bytes


def child(kind, path):
    """Load one format, then time searches from the same random starts."""
    import numpy as np
    from scipy.sparse.csgraph import dijkstra
    from graph import WalkGraph  # imports first, so they don't count as load time

    tracemalloc.start()
    start = time.perf_counter()
    if kind == "json":
        g = WalkGraph.from_file(path)
        node_ids = list(g.coords)
    else:
        matrix, arrays = load_arrays(path)
        node_ids = arrays["ids"].tolist()
    load_s = time.perf_counter() - start
    held_mb = tracemalloc.get_traced_memory()[0] / 1e6
    tracemalloc.stop()
    rss_mb = peak_rss_mb()  # whole process: Python, libraries, graph, and parsing

    rng = random.Random(15)
    starts = rng.sample(range(len(node_ids)), SAMPLE_STARTS)
    reached, times = [], []
    for i in starts:
        t = time.perf_counter()
        if kind == "json":
            result = g.reachable_within(node_ids[i], MINUTES)
        else:
            dist = dijkstra(matrix, indices=i, limit=MINUTES * WALK_M_PER_MIN)
            hit = np.flatnonzero(np.isfinite(dist))
            result = dict(zip((node_ids[j] for j in hit), (dist[hit] / WALK_M_PER_MIN).tolist()))
        times.append(time.perf_counter() - t)
        reached.append({str(n): round(m, 3) for n, m in result.items()})

    times.sort()
    print(json.dumps({
        "load_s": round(load_s, 2), "held_mb": round(held_mb, 1), "rss_mb": round(rss_mb, 1),
        "search_ms_median": round(times[len(times) // 2] * 1000, 1),
        "search_ms_max": round(times[-1] * 1000, 1),
        "reached": reached,
    }))


def run_child(kind, path):
    out = subprocess.run([sys.executable, __file__, "--child", kind, str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out.strip().splitlines()[-1])


def agree(a, b):
    """True if two searches reach the same nodes in the same times. The two
    versions add up lengths in different ways, so a node right on the 15-minute
    line can be just inside in one and just outside in the other; allow that."""
    for node in a.keys() | b.keys():
        if node in a and node in b:
            if abs(a[node] - b[node]) > 0.01:
                return False
        elif (a.get(node) or b.get(node)) < MINUTES - 0.01:
            return False
    return True


def report(json_path):
    json_path = Path(json_path)
    npz_path = json_path.with_suffix(".npz")
    meta = json.loads(json_path.read_text())
    nodes, edges = len(meta["nodes"]), len(meta["edges"])
    del meta
    to_arrays(json_path, npz_path)

    as_json = run_child("json", json_path)
    as_arrays = run_child("npz", npz_path)
    same = all(agree(a, b) for a, b in zip(as_json["reached"], as_arrays["reached"]))

    print(f"\nGraph: {json_path}")
    print(f"{nodes:,} nodes, {edges:,} edges")
    print(f"{'':28}{'JSON + dicts (now)':>20}{'NumPy arrays':>16}")
    rows = [
        ("File size (MB)", json_path.stat().st_size / 1e6, npz_path.stat().st_size / 1e6),
        ("Load time (s)", as_json["load_s"], as_arrays["load_s"]),
        ("Memory held (MB)", as_json["held_mb"], as_arrays["held_mb"]),
        ("Process peak memory (MB)", as_json["rss_mb"], as_arrays["rss_mb"]),
        ("15-min search, median (ms)", as_json["search_ms_median"], as_arrays["search_ms_median"]),
        ("15-min search, slowest (ms)", as_json["search_ms_max"], as_arrays["search_ms_max"]),
    ]
    for label, x, y in rows:
        print(f"{label:28}{x:>20.1f}{y:>16.1f}")
    reached = sorted(len(r) for r in as_json["reached"])
    print(f"Nodes reached per search: median {reached[len(reached) // 2]:,}, most {reached[-1]:,}")
    print(f"Both versions reach the same nodes in the same times: {'yes' if same else 'NO'}")
    print("Render's free plan has 512 MB of memory for everything the server holds.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--graph", help="measure this JSON graph instead of downloading")
    parser.add_argument("--child", nargs=2, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        child(*args.child)
    elif args.graph:
        report(args.graph)
    else:
        path = download()
        # Measure in a fresh process: a process started from this one can
        # report this one's peak memory, which is large after the download.
        subprocess.run([sys.executable, __file__, "--graph", str(path)], check=True)
