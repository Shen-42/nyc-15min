from collections import Counter
from pathlib import Path

import pytest

from amenities import CATEGORIES, load_amenities, reachable_amenities
from graph import WalkGraph

DATA = Path(__file__).parent / "data"
AMENITIES_FILE = DATA / "amenities.json"
GRAPH_FILE = DATA / "walk_graph.npz"
needs_data = pytest.mark.skipif(
    not (AMENITIES_FILE.exists() and GRAPH_FILE.exists()),
    reason="run scripts/build_graph.py and scripts/build_amenities.py first",
)


def place(id, category, nodes):
    return {"id": id, "category": category, "name": None, "lat": 0, "lng": 0, "nodes": nodes}


def test_places_listed_twice_load_once(tmp_path):
    """Card 15: a place on the line between two download pieces came back
    twice, and its two map markers had the same key."""
    import json

    path = tmp_path / "amenities.json"
    path.write_text(json.dumps([place("way/1", "park", [1]), place("way/1", "park", [1]), place("way/1", "school", [1])]))
    assert [(p["category"], p["id"]) for p in load_amenities(path)] == [("park", "way/1"), ("school", "way/1")]


def test_unreached_places_are_left_out():
    places = [place("a", "grocery", [1]), place("b", "grocery", [9])]
    reached = reachable_amenities(places, {1: 2.0, 2: 5.0})
    assert [p["id"] for p in reached] == ["a"]


def test_a_park_counts_from_its_nearest_node():
    # A park with three paths inside. You reach its closest one in 3 minutes.
    reached = reachable_amenities([place("p", "park", [5, 6, 7])], {5: 9.0, 6: 3.0, 8: 1.0})
    assert reached[0]["minutes"] == 3.0


def test_offset_is_added_and_closest_comes_first():
    places = [place("far", "school", [2]), place("near", "pharmacy", [1])]
    reached = reachable_amenities(places, {1: 1.0, 2: 4.0}, offset=0.5)
    assert [(p["id"], p["minutes"]) for p in reached] == [("near", 1.5), ("far", 4.5)]


@pytest.fixture(scope="module")
def data():
    return WalkGraph.from_file(GRAPH_FILE), load_amenities(AMENITIES_FILE)


@needs_data
def test_every_category_has_places(data):
    _, amenities = data
    counts = Counter(a["category"] for a in amenities)
    for category in CATEGORIES:
        assert counts[category] > 10, f"only {counts[category]} {category} places"
    # Manhattan has about 150 subway stations and the city 472. Allow for how
    # OSM splits big complexes, and for either data set (card 15).
    assert 80 <= counts["subway"] <= 700


@needs_data
def test_times_square_reaches_every_category(data):
    graph, amenities = data
    start, _ = graph.nearest_node(40.7580, -73.9855)
    reached = reachable_amenities(amenities, graph.reachable_within(start, 15))
    found = {p["category"] for p in reached}
    assert found == set(CATEGORIES), f"missing: {set(CATEGORIES) - found}"


@needs_data
def test_central_park_is_right_across_fifth_avenue(data):
    graph, amenities = data
    start, _ = graph.nearest_node(40.7724, -73.9653)  # 5th Ave and 72nd St
    reached = reachable_amenities(amenities, graph.reachable_within(start, 15))
    central_park = [p for p in reached if p["name"] == "Central Park"]
    assert central_park and central_park[0]["minutes"] < 3


@needs_data
def test_index_matches_checking_every_place_on_real_searches(data):
    """PlaceIndex (card 15) gives the same answer as the plain loop it replaced."""
    import random

    from amenities import PlaceIndex

    graph, amenities = data
    index = PlaceIndex(amenities)
    random.seed(4)
    for _ in range(25):
        start = graph.ids[random.randrange(len(graph))].item()
        times = graph.reachable_within(start, 15)
        expected = []
        for place in amenities:
            best = min((times[n] for n in place["nodes"] if n in times), default=None)
            if best is not None:
                expected.append({k: place[k] for k in ("id", "category", "name", "lat", "lng")} | {"minutes": round(best + 0.4, 1)})
        expected.sort(key=lambda p: p["minutes"])
        assert index.reachable(times, 0.4) == expected
