from pathlib import Path

import pytest
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from graph import WALK_SPEED_M_PER_MIN, WalkGraph
from walk_area import cut_path, load_land, load_water, walking_area

GRAPH_FILE = Path(__file__).parent / "data" / "walk_graph.json"
LAND_FILE = Path(__file__).parent / "data" / "manhattan-boundary.json"
WATER_FILE = Path(__file__).parent / "data" / "water.json"
needs_water = pytest.mark.skipif(not WATER_FILE.exists(), reason="run scripts/build_water.py first")

# The same trimming shape the server uses: shoreline minus lakes and ponds.
LAND = load_land(LAND_FILE)
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
    assert len(manhattan.shapes) > 1000


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
