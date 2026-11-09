"""Tests for scripts/coast.py: creeks the borough shoreline counts as land."""

import sys
from pathlib import Path

from shapely.geometry import LineString, box

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from coast import creeks_on_land, sea_areas  # noqa: E402

# A made-up city 10 km across: land on the left half, sea on the right, and a
# creek 100 m wide cutting 2 km into the land along y = 0.05. The borough
# shoreline (land) runs straight across the creek's mouth; the coastline
# goes up one bank and back down the other.
CITY = box(0, 0, 0.1, 0.1)
LAND = box(0, 0, 0.05, 0.1)
COAST = [LineString([(0.05, 0.13), (0.05, 0.0505), (0.03, 0.0505), (0.03, 0.0495), (0.05, 0.0495), (0.05, -0.03)])]
CREEK_LINE = LineString([(0.032, 0.05), (0.07, 0.05)])
PIER = LineString([(0.05, 0.08), (0.049, 0.08)])  # a line that barely enters the land


def test_sea_is_the_side_off_the_land():
    sea = sea_areas(COAST, LAND, CITY)
    assert sea.contains(box(0.06, 0.01, 0.09, 0.09).centroid)
    assert sea.contains(LineString([(0.035, 0.05), (0.045, 0.05)]))  # the creek
    assert not sea.contains(box(0.01, 0.01, 0.02, 0.02).centroid)  # the land


def test_creek_on_land_is_found_and_named():
    found = creeks_on_land(COAST, LAND, CITY, [("Test Creek", CREEK_LINE), ("Pier Slip", PIER)], min_area=1e-8)
    assert [name for name, _ in found] == ["Test Creek"]
    _, piece = found[0]
    assert abs(piece.area - 0.02 * 0.001) < 1e-9  # 2 km by 100 m


def test_nothing_without_a_line_through_it():
    assert creeks_on_land(COAST, LAND, CITY, [("Pier Slip", PIER)], min_area=1e-8) == []
