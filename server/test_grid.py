from grid import Grid
from scoring import CATEGORY_SETTINGS, settings_with_weights

CATEGORIES = list(CATEGORY_SETTINGS)


def make_grid(rows):
    """A grid from rows of six category scores."""
    return Grid({
        "meta": {"categories": CATEGORIES},
        "cells": [[40.75, -73.99, row, [1] * 6] for row in rows],
        "gaps": {},
    })


def test_rank_is_the_share_of_cells_scoring_lower():
    grid = make_grid([[s] * 6 for s in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)])
    assert grid.rank(55, CATEGORY_SETTINGS) == 50
    assert grid.rank(10, CATEGORY_SETTINGS) == 0  # ties don't count as lower
    assert grid.rank(101, CATEGORY_SETTINGS) == 100


def test_rank_uses_the_same_weights_as_the_score():
    # Cell A is great for parks only, cell B for groceries only.
    a = [0, 0, 0, 0, 100, 0]
    b = [100, 0, 0, 0, 0, 0]
    grid = make_grid([a, b])
    parks_only = settings_with_weights({c: (3 if c == "park" else 0) for c in CATEGORIES})
    assert grid.rank(50, parks_only) == 50  # A scores 100, B scores 0
    groceries_only = settings_with_weights({c: (3 if c == "grocery" else 0) for c in CATEGORIES})
    assert grid.rank(100, groceries_only) == 50
