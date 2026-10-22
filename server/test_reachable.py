"""Tests for WalkGraph.reachable_within (card 4). They fail until you write it."""

from pathlib import Path

import pytest

from graph import WALK_SPEED_M_PER_MIN, WalkGraph

M = WALK_SPEED_M_PER_MIN  # meters you can walk in one minute (80)


def make_graph(edges):
    """Build a WalkGraph from edges given in minutes. Coordinates don't matter here."""
    node_ids = sorted({n for a, b, _ in edges for n in (a, b)})
    nodes = [[n, 40.75, -73.99] for n in node_ids]
    return WalkGraph(nodes, [[a, b, minutes * M] for a, b, minutes in edges])


def test_start_is_zero():
    g = make_graph([(1, 2, 3)])
    assert g.reachable_within(1, 15)[1] == 0


def test_times_add_up_along_a_street():
    # 1 --3 min-- 2 --4 min-- 3
    g = make_graph([(1, 2, 3), (2, 3, 4)])
    times = g.reachable_within(1, 15)
    assert times[2] == pytest.approx(3)
    assert times[3] == pytest.approx(7)


def test_stops_at_the_limit():
    # 1 --10-- 2 --10-- 3. Node 3 is 20 minutes away, past the limit.
    g = make_graph([(1, 2, 10), (2, 3, 10)])
    times = g.reachable_within(1, 15)
    assert 2 in times
    assert 3 not in times


def test_node_exactly_at_the_limit_is_included():
    g = make_graph([(1, 2, 15)])
    assert g.reachable_within(1, 15)[2] == pytest.approx(15)


def test_picks_the_shorter_route():
    # Two ways from 1 to 4:  1-2-4 takes 2 + 2 = 4 min,  1-3-4 takes 1 + 9 = 10 min.
    # Node 3 is popped first (1 min), so a first guess for 4 is 10 min.
    # A correct Dijkstra replaces it with 4.
    g = make_graph([(1, 2, 2), (2, 4, 2), (1, 3, 1), (3, 4, 9)])
    assert g.reachable_within(1, 15)[4] == pytest.approx(4)


def test_walking_works_both_ways():
    g = make_graph([(1, 2, 5)])
    assert g.reachable_within(2, 15)[1] == pytest.approx(5)


def test_disconnected_nodes_are_not_reached():
    # 1-2 and 3-4 are separate pieces, like Manhattan and Roosevelt Island.
    g = make_graph([(1, 2, 1), (3, 4, 1)])
    assert set(g.reachable_within(1, 15)) == {1, 2}


# On the real Manhattan graph. Skipped if the graph file is missing.
GRAPH_FILE = Path(__file__).parent / "data" / "walk_graph.json"


@pytest.mark.skipif(not GRAPH_FILE.exists(), reason="run scripts/build_graph.py first")
def test_times_square_15_minutes():
    g = WalkGraph.from_file(GRAPH_FILE)
    start, _ = g.nearest_node(40.7580, -73.9855)
    times = g.reachable_within(start, 15)
    assert len(times) > 500
    assert max(times.values()) <= 15
    # Bryant Park (about 600 m away) should be in reach.
    bryant, _ = g.nearest_node(40.7536, -73.9832)
    assert bryant in times
