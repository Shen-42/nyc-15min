"""The precomputed city grid (cards 12 and 15): every 100 m of land, scored by
scripts/build_grid.py, one file per borough. Used to rank a clicked spot
against its borough and the whole city. The site reads the same files to
draw the score map and gap finder."""

import json
from pathlib import Path

import numpy as np

# Values per square in a file's flat "cells" list (see build_grid.py).
FIELDS_BEFORE_SCORES = 2  # col, row


class Grid:
    def __init__(self, files):
        """files: the parsed grid-<borough>.json files."""
        self.categories = files[0]["meta"]["categories"]
        self.boroughs = [f["meta"]["borough"] for f in files]
        n_cat = len(self.categories)
        park_bit = 1 << n_cat
        scores, borough = [], []
        for b, f in enumerate(files):
            cells = np.asarray(f["cells"], dtype=np.int64).reshape(-1, FIELDS_BEFORE_SCORES + n_cat + 1)
            # Squares mostly inside parks are left out: nobody lives there, so
            # they'd only make everywhere else look better.
            lived_in = (cells[:, -1] & park_bit) == 0
            scores.append(cells[lived_in, FIELDS_BEFORE_SCORES:FIELDS_BEFORE_SCORES + n_cat])
            borough.append(np.full(lived_in.sum(), b))
        self.scores = np.concatenate(scores).astype(np.float64)
        self.borough = np.concatenate(borough)
        self._sorted = {}

    @classmethod
    def from_dir(cls, data_dir):
        """The grid from data_dir/grid-*.json, or None if there are none."""
        paths = sorted(Path(data_dir).glob("grid-*.json"))
        return cls([json.loads(p.read_text()) for p in paths]) if paths else None

    def __len__(self):
        return len(self.scores)

    def _totals(self, weights):
        """Every square's overall score with these weights, sorted, for the
        city and for each borough. weights is a tuple in the order of
        self.categories, so it can be a cache key."""
        if weights not in self._sorted:
            if len(self._sorted) >= 64:
                self._sorted.clear()
            w = np.asarray(weights, dtype=np.float64)
            # np.round rounds halves to even, like Python's round() in scoring.py.
            totals = np.round(self.scores @ w / w.sum())
            self._sorted[weights] = (
                np.sort(totals),
                {b: np.sort(totals[self.borough == i]) for i, b in enumerate(self.boroughs)},
            )
        return self._sorted[weights]

    def rank(self, score, settings, borough=None):
        """The share (0-100) of the city's squares, and of the borough's, that
        score lower than `score` with the same category weights.
        Returns {"city": ..., "borough": ... or None, "name": borough}."""
        weights = tuple(settings[c]["weight"] for c in self.categories)
        city, by_borough = self._totals(weights)

        def share(totals):
            return round(100 * int(np.searchsorted(totals, score, side="left")) / len(totals)) if len(totals) else None

        mine = by_borough.get(borough)
        return {"city": share(city), "borough": share(mine) if mine is not None else None, "name": borough}
