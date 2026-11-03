from pathlib import Path

import pytest

from grid import Grid
from scoring import CATEGORY_SETTINGS, settings_with_weights

CATEGORIES = list(CATEGORY_SETTINGS)
PARK = 1 << len(CATEGORIES)
DATA = Path(__file__).parent / "data"


def borough_file(name, rows, flags=None):
    """A grid file for one borough, from rows of six category scores."""
    flags = flags or [0] * len(rows)
    cells = []
    for i, (row, flag) in enumerate(zip(rows, flags)):
        cells += [i, 0, *row, flag]
    return {"meta": {"borough": name, "categories": CATEGORIES}, "cells": cells, "gaps": {}}


def make_grid(rows):
    return Grid([borough_file("Manhattan", rows)])


def test_rank_is_the_share_of_cells_scoring_lower():
    grid = make_grid([[s] * 6 for s in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)])
    assert grid.rank(55, CATEGORY_SETTINGS)["city"] == 50
    assert grid.rank(10, CATEGORY_SETTINGS)["city"] == 0  # ties don't count as lower
    assert grid.rank(101, CATEGORY_SETTINGS)["city"] == 100


def test_rank_uses_the_same_weights_as_the_score():
    # Cell A is great for parks only, cell B for groceries only.
    a = [0, 0, 0, 0, 100, 0]
    b = [100, 0, 0, 0, 0, 0]
    grid = make_grid([a, b])
    parks_only = settings_with_weights({c: (3 if c == "park" else 0) for c in CATEGORIES})
    assert grid.rank(50, parks_only)["city"] == 50  # A scores 100, B scores 0
    groceries_only = settings_with_weights({c: (3 if c == "grocery" else 0) for c in CATEGORIES})
    assert grid.rank(100, groceries_only)["city"] == 50


def test_rank_against_the_borough_and_the_city():
    # Manhattan scores 80 and 90; Staten Island 10, 20, 30.
    grid = Grid([
        borough_file("Manhattan", [[80] * 6, [90] * 6]),
        borough_file("Staten Island", [[10] * 6, [20] * 6, [30] * 6]),
    ])
    rank = grid.rank(85, CATEGORY_SETTINGS, "Manhattan")
    assert rank == {"city": 80, "borough": 50, "name": "Manhattan"}  # 4 of 5 in the city, 1 of 2 in Manhattan
    assert grid.rank(85, CATEGORY_SETTINGS, None)["borough"] is None  # just off the shore


def test_park_squares_are_left_out():
    grid = Grid([borough_file("Manhattan", [[10] * 6, [90] * 6], flags=[0, PARK])])
    assert len(grid) == 1
    assert grid.rank(50, CATEGORY_SETTINGS)["city"] == 100


@pytest.mark.skipif(not list(DATA.glob("grid-*.json")), reason="run scripts/build_grid.py first")
def test_the_city_grid_has_every_borough():
    grid = Grid.from_dir(DATA)
    assert sorted(grid.boroughs) == ["Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"]
    assert len(grid) > 50_000
