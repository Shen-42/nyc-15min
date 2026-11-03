import math
from pathlib import Path

import pytest

from graph import WalkGraph, distance_m

GRAPH_FILE = Path(__file__).parent / "data" / "walk_graph.npz"

# A tiny made-up graph: three nodes in a line along a street.
#   1 ---- 2 ---- 3
SMALL_NODES = [
    [1, 40.7500, -73.9900],
    [2, 40.7510, -73.9900],
    [3, 40.7520, -73.9900],
]
SMALL_EDGES = [[1, 2, 111.2], [2, 3, 111.2]]


def test_distance_one_block():
    # 0.001 degrees of latitude is about 111 meters anywhere on Earth.
    assert distance_m(40.75, -73.99, 40.751, -73.99) == pytest.approx(111.2, abs=0.5)


def test_edges_go_both_ways():
    g = WalkGraph(SMALL_NODES, SMALL_EDGES)
    assert (2, 111.2) in g.neighbors(1)
    assert (1, 111.2) in g.neighbors(2)
    assert len(g.neighbors(2)) == 2


def test_edge_points_follow_the_curve_both_ways():
    # A curved path from 1 to 2 with one point in between.
    g = WalkGraph(
        [[1, 40.7500, -73.9900], [2, 40.7510, -73.9900]],
        [[1, 2, 150.0, [[40.7505, -73.9895]]]],
    )
    assert g.edge_points(1, 2) == [(40.75, -73.99), (40.7505, -73.9895), (40.751, -73.99)]
    assert g.edge_points(2, 1) == [(40.751, -73.99), (40.7505, -73.9895), (40.75, -73.99)]
    assert g.neighbors(1) == [(2, 150.0)]


def test_nearest_node_small_graph():
    g = WalkGraph(SMALL_NODES, SMALL_EDGES)
    node_id, dist = g.nearest_node(40.7512, -73.9901)
    assert node_id == 2
    assert dist < 30


# The tests below use the real Manhattan graph and are skipped until you build it.
needs_graph = pytest.mark.skipif(not GRAPH_FILE.exists(), reason="run scripts/build_graph.py first")

KNOWN_PLACES = {
    "Times Square": (40.7580, -73.9855),
    "Washington Square Arch": (40.7312, -73.9971),
    "Broadway and 116th St (Columbia)": (40.8081, -73.9640),
    "Roosevelt Island tram station": (40.7570, -73.9536),
}


@pytest.fixture(scope="module")
def manhattan():
    return WalkGraph.from_file(GRAPH_FILE)


@needs_graph
def test_graph_size(manhattan):
    assert len(manhattan) > 10_000
    assert manhattan.edge_count > 10_000


@needs_graph
@pytest.mark.parametrize("name", KNOWN_PLACES)
def test_known_places_are_near_a_node(manhattan, name):
    lat, lng = KNOWN_PLACES[name]
    node_id, dist = manhattan.nearest_node(lat, lng)
    assert dist < 75, f"{name}: nearest node is {dist:.0f} m away"
    assert len(manhattan.neighbors(node_id)) > 0


@needs_graph
def test_nearest_node_matches_checking_every_node(manhattan):
    import random

    import numpy as np

    random.seed(0)
    lat_all, lng_all = np.radians(manhattan.lat), np.radians(manhattan.lng)
    for _ in range(200):
        lat = random.uniform(40.70, 40.88)
        lng = random.uniform(-74.02, -73.91)
        # Haversine to every node at once, the slow but sure way.
        a = (np.sin((lat_all - math.radians(lat)) / 2) ** 2
             + math.cos(math.radians(lat)) * np.cos(lat_all) * np.sin((lng_all - math.radians(lng)) / 2) ** 2)
        best = int(np.argmin(a))
        node, dist = manhattan.nearest_node(lat, lng)
        assert dist == pytest.approx(distance_m(lat, lng, manhattan.lat[best], manhattan.lng[best]))


def python_dijkstra(graph, start, max_minutes, speed=80, node_penalty=None):
    """The search as it was before card 15, in plain Python, to check scipy's against."""
    import heapq

    queue, best = [(0, start)], {start: 0}
    while queue:
        minutes, node = heapq.heappop(queue)
        if minutes > best[node]:
            continue
        for neighbor, length_m in graph.neighbors(node):
            new = minutes + length_m / speed + (node_penalty or {}).get(neighbor, 0)
            if new <= max_minutes and (neighbor not in best or new < best[neighbor]):
                best[neighbor] = new
                heapq.heappush(queue, (new, neighbor))
    return best


def same_times(a, b, max_minutes):
    """Same nodes at the same times. A node within a hair of the limit may be
    in one and not the other, since the two add up lengths differently."""
    for node in a.keys() | b.keys():
        if node in a and node in b:
            assert a[node] == pytest.approx(b[node], abs=1e-6)
        else:
            assert (a.get(node) or b.get(node)) > max_minutes - 1e-6


@needs_graph
def test_search_matches_the_original_python_dijkstra(manhattan):
    import random

    random.seed(1)
    penalty = {n: 3 for n in manhattan.curb_nodes[::3]}
    for _ in range(20):
        start = manhattan.ids[random.randrange(len(manhattan))].item()
        same_times(manhattan.reachable_within(start, 15), python_dijkstra(manhattan, start, 15), 15)
        same_times(
            manhattan.reachable_within(start, 12, 48, penalty),
            python_dijkstra(manhattan, start, 12, 48, penalty),
            12,
        )


def test_save_and_load_keep_everything(tmp_path):
    g = WalkGraph(
        [[30, 40.7520, -73.9900], [10, 40.7500, -73.9900], [20, 40.7510, -73.9900]],
        [[10, 20, 150.0, [[40.7505, -73.9895]]], [20, 30, 111.2]],
        meta={"built": "2026-11-03"},
        curb_nodes=[20],
        streets={"20": ["Broadway", "W 42nd St"]},
    )
    g.save(tmp_path / "g.npz")
    h = WalkGraph.from_file(tmp_path / "g.npz")
    assert list(h.coords) == [10, 20, 30]
    assert h.edge_points(20, 10) == g.edge_points(20, 10) == [(40.751, -73.99), (40.7505, -73.9895), (40.75, -73.99)]
    assert h.neighbors(20) == g.neighbors(20)
    assert h.meta == {"built": "2026-11-03"} and h.curb_nodes == [20] and h.streets == {"20": ["Broadway", "W 42nd St"]}
    assert h.reachable_within(10, 15) == g.reachable_within(10, 15)


def test_zero_length_edges_are_walkable():
    # Two OpenStreetMap nodes at the same spot, joined by a 0 m edge.
    g = WalkGraph([[1, 40.75, -73.99], [2, 40.75, -73.99], [3, 40.751, -73.99]], [[1, 2, 0.0], [2, 3, 80.0]])
    assert g.reachable_within(1, 15) == {1: 0.0, 2: 0.0, 3: 1.0}


def test_penalty_tables_are_not_mixed_up():
    g = WalkGraph([[1, 0, 0], [2, 0, 0]], [[1, 2, 80.0]])
    assert g.reachable_within(1, 15, node_penalty={2: 3})[2] == pytest.approx(4)
    assert g.reachable_within(1, 15, node_penalty={2: 5})[2] == pytest.approx(6)
    assert g.reachable_within(1, 15)[2] == pytest.approx(1)
