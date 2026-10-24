from pathlib import Path

import pytest

from graph import WalkGraph, distance_m

GRAPH_FILE = Path(__file__).parent / "data" / "walk_graph.json"

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
def test_grid_finds_the_same_node_as_checking_every_node(manhattan):
    import random

    random.seed(0)
    for _ in range(200):
        lat = random.uniform(40.70, 40.88)
        lng = random.uniform(-74.02, -73.91)
        best = min(manhattan.coords, key=lambda n: distance_m(lat, lng, *manhattan.coords[n]))
        node, dist = manhattan.nearest_node(lat, lng)
        assert dist == pytest.approx(distance_m(lat, lng, *manhattan.coords[best]))
