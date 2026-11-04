import json
from pathlib import Path

import pytest
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from graph import WALK_SPEED_M_PER_MIN, WalkGraph
from walk_area import Outlines, cut_path, empty_islands, row_runs, load_boroughs, load_land, load_water, walking_area

GRAPH_FILE = Path(__file__).parent / "data" / "walk_graph.npz"
WATER_FILE = Path(__file__).parent / "data" / "water.json"
needs_water = pytest.mark.skipif(not WATER_FILE.exists(), reason="run scripts/build_water.py first")

# The same trimming shape the server uses: shoreline minus lakes and ponds.
LAND = load_land()
if WATER_FILE.exists():
    LAND = LAND.difference(unary_union([s for _, s in load_water(WATER_FILE)]))
needs_graph = pytest.mark.skipif(not GRAPH_FILE.exists(), reason="run scripts/build_graph.py first")


def test_cut_path_halfway_along_a_bend():
    # An L-shaped path: 100 m east, then 100 m north. Half of it ends at the corner.
    path = [(0, 0), (100, 0), (100, 100)]
    assert cut_path(path, 0.5) == [(0, 0), (100, 0)]
    assert cut_path(path, 0.75) == [(0, 0), (100, 0), (100, 50)]
    assert cut_path(path, 1.0)[-1] == (100, 100)


@pytest.fixture(scope="module")
def manhattan():
    return WalkGraph.from_file(GRAPH_FILE)


def area_from(g, lat, lng, minutes=15):
    start, _ = g.nearest_node(lat, lng)
    times = g.reachable_within(start, minutes)
    return shape(walking_area(g, start, times, minutes, WALK_SPEED_M_PER_MIN, LAND))


def contains(area, lat, lng):
    return area.contains(Point(lng, lat))  # shapely uses (x, y) = (lng, lat)


@needs_graph
def test_times_square(manhattan):
    area = area_from(manhattan, 40.7580, -73.9855)
    assert area.geom_type in ("Polygon", "MultiPolygon")
    assert contains(area, 40.7580, -73.9855)  # where you clicked
    assert contains(area, 40.7536, -73.9832)  # Bryant Park, about 600 m
    assert contains(area, 40.7527, -73.9772)  # Grand Central, about 900 m
    assert not contains(area, 40.7359, -73.9906)  # Union Square, about 2.5 km


@needs_graph
def test_block_interiors_are_filled(manhattan):
    area = area_from(manhattan, 40.7580, -73.9855)
    # Middle of the block between 6th/7th Ave and 44th/45th St.
    assert contains(area, 40.7568, -73.9843)


@needs_graph
def test_does_not_spill_into_the_hudson(manhattan):
    area = area_from(manhattan, 40.7295, -74.0080)  # West St near Pier 40
    assert not contains(area, 40.7300, -74.0180)  # open water past the piers
    assert contains(area, 40.7280, -74.0050)  # Hudson Square, a few blocks inland


@needs_graph
def test_paths_keep_their_curves(manhattan):
    # Rebuilt graphs store the points along curved paths.
    assert manhattan.curved_edge_count > 1000


@needs_graph
@needs_water
def test_reservoir_water_is_not_covered(manhattan):
    # Start on Fifth Avenue next to the Reservoir.
    area = area_from(manhattan, 40.7838, -73.9592)
    assert not contains(area, 40.7855, -73.9628)  # middle of the Reservoir


@needs_graph
def test_east_river_edge_is_trimmed_to_the_shoreline(manhattan):
    area = area_from(manhattan, 40.7635, -73.9580)  # E 65th St near York Ave
    # Less than 1 square meter of the area may sit outside Manhattan's outline.
    outside = area.difference(LAND)
    assert outside.area * (111_000 * 85_000) < 1
    assert not contains(area, 40.7600, -73.9545)  # East River off 61st St


@needs_water
def test_water_file_has_the_big_lakes():
    water = load_water(WATER_FILE)
    union = unary_union([s for _, s in water])
    assert union.contains(Point(-73.9628, 40.7855))  # the Reservoir
    assert union.contains(Point(-73.9511, 40.7963))  # Harlem Meer, open water


@needs_graph
@needs_water
def test_harlem_meer_is_not_covered(manhattan):
    area = area_from(manhattan, 40.7966, -73.9496)  # Fifth Ave and 110th St
    assert not contains(area, 40.7963, -73.9511)  # Harlem Meer, open water


@needs_graph
@needs_water
def test_lawns_are_filled(manhattan):
    area = area_from(manhattan, 40.7788, -73.9665)  # Great Lawn, east path
    assert contains(area, 40.7812, -73.9665)  # middle of the Great Lawn


# ---- The five boroughs (card 15) ----

BOROUGH_SPOTS = {
    "Manhattan": (40.7580, -73.9855),  # Times Square
    "Brooklyn": (40.6782, -73.9442),  # Crown Heights
    "Queens": (40.7590, -73.8303),  # Flushing
    "Bronx": (40.8448, -73.8648),  # Parkchester
    "Staten Island": (40.5795, -74.1502),  # New Springville
}


def test_each_borough_has_its_land():
    boroughs = load_boroughs()
    assert sorted(boroughs) == sorted(BOROUGH_SPOTS)
    for name, (lat, lng) in BOROUGH_SPOTS.items():
        inside = [other for other, land in boroughs.items() if land.contains(Point(lng, lat))]
        assert inside == [name]


def test_the_city_land_leaves_out_the_rivers_and_new_jersey():
    assert not LAND.contains(Point(-73.9960, 40.7060))  # East River under the middle of the Brooklyn Bridge
    assert not LAND.contains(Point(-74.0200, 40.7400))  # Hudson River
    assert not LAND.contains(Point(-74.0431, 40.7178))  # Jersey City


def test_outlines_find_the_shape_a_point_is_in():
    from shapely.geometry import box

    outlines = Outlines([("A", box(0, 0, 1, 1)), (None, box(2, 0, 3, 1))])
    assert outlines.find(Point(0.5, 0.5)) == (True, "A")
    assert outlines.find(Point(2.5, 0.5)) == (True, None)  # an unnamed park
    assert outlines.find(Point(1.5, 0.5)) == (False, None)
    assert len(outlines) == 2 and list(outlines)[0][0] == "A"


def test_unnamed_outlines_are_called_by_their_kind(tmp_path):
    from walk_area import load_parks

    square = [[40.70, -73.90], [40.70, -73.89], [40.71, -73.89], [40.71, -73.90], [40.70, -73.90]]
    path = tmp_path / "parks.json"
    path.write_text(json.dumps([
        {"name": "Woodlawn Cemetery", "kind": "cemetery", "rings": [square]},
        {"name": None, "kind": "cemetery", "rings": [square]},
        {"name": None, "rings": [square]},  # written before card 15, with no kind
    ]))
    assert [name for name, _ in load_parks(path)] == ["Woodlawn Cemetery", "a cemetery", "a park"]


def test_islands_with_no_paths_are_found(tmp_path):
    """Card 15: a borough's mainland, an island with streets, a marsh island
    with none, and a pier with none that touches the mainland."""
    import numpy as np

    def square(lat, lng, size):
        return [[lat, lng], [lat + size, lng], [lat + size, lng + size], [lat, lng + size]]

    path = tmp_path / "boroughs.json"
    path.write_text(json.dumps({"boroughs": {"Testboro": [
        square(40.0, -74.0, 0.1),        # mainland
        square(40.0, -73.85, 0.02),      # island with streets
        square(40.05, -73.88, 0.01),     # marsh island, 2 km out
        square(40.05, -73.9, 0.001),     # pier joined to the mainland
    ]}}))
    rng = np.random.default_rng(1)
    lat = np.concatenate([40.0 + rng.random(50) * 0.1, 40.0 + rng.random(20) * 0.02, [40.055]])
    lng = np.concatenate([-74.0 + rng.random(50) * 0.1, -73.85 + rng.random(20) * 0.02, [-73.875]])
    found = empty_islands(lat, lng, path=path)
    assert len(found) == 1
    name, land = found[0]
    assert name is None
    assert land.contains(Point(-73.875, 40.055))


def test_row_runs_cover_the_marked_squares_once():
    import numpy as np

    marked = np.array([[0, 1, 1, 0], [0, 1, 1, 1], [1, 0, 0, 1]], dtype=bool)
    rects = row_runs(marked)
    covered = np.zeros(marked.shape, dtype=int)
    for col0, row0, col1, row1 in rects:
        covered[row0:row1, col0:col1] += 1
    assert (covered == marked).all()


def test_area_of_one_street_walked_partway():
    """Card 15: the area drawn on a grid of squares. A straight street east
    from corner 1 through corner 2 (800 m) to corner 3 (800 m more). The walk
    reaches corner 2 at minute 10, so with 5 minutes left it gets 400 m
    toward corner 3: a strip 1,200 m long and 80 m wide with round ends."""
    import math

    m_per_deg_lng = 111_320 * math.cos(math.radians(40.7))
    east = 800 / m_per_deg_lng
    g = WalkGraph(
        [[1, 40.7, -74.0], [2, 40.7, -74.0 + east], [3, 40.7, -74.0 + 2 * east]],
        [[1, 2, 800.0, [[40.7, -74.0 + east / 2]]], [2, 3, 800.0]],
    )
    area = shape(walking_area(g, 1, {1: 0.0, 2: 10.0}, 15, 80, cell_m=5))
    assert contains(area, 40.7, -74.0 + 1100 / m_per_deg_lng)
    assert not contains(area, 40.7, -74.0 + 1300 / m_per_deg_lng)
    assert contains(area, 40.7 + 30 / 110_540, -74.0 + 600 / m_per_deg_lng)  # 30 m off the street
    assert not contains(area, 40.7 + 50 / 110_540, -74.0 + 600 / m_per_deg_lng)  # 50 m off it
    # The squares the street passes through are marked whole, so the strip
    # comes out up to half a square (2.5 m) wider on each side: about 6%
    # here, under 1% for a real walk, whose outline is short for its area.
    expected_m2 = 1200 * 80 + math.pi * 40**2
    assert 0.97 < area.area * m_per_deg_lng * 110_540 / expected_m2 < 1.10
