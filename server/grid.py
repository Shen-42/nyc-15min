"""The precomputed Manhattan grid (card 12): every 100 m of land, scored by
scripts/build_grid.py. Used to rank a clicked point and to draw the heat map."""

import bisect
import json
from functools import lru_cache
from pathlib import Path


class Grid:
    def __init__(self, data):
        self.data = data
        self.categories = data["meta"]["categories"]
        # Each cell's score in each category, in the order of self.categories.
        # Cells mostly inside parks (cell[4] == 1) are left out: nobody
        # lives there, so they'd only make everywhere else look better.
        self.scores = [cell[2] for cell in data["cells"] if not (len(cell) > 4 and cell[4])]

    @classmethod
    def from_file(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def __len__(self):
        return len(self.scores)

    @lru_cache(maxsize=64)
    def _sorted_totals(self, weights):
        """Every cell's overall score with these weights, sorted. weights is a
        tuple in the order of self.categories, so it can be a cache key."""
        total = sum(weights)
        return sorted(
            round(sum(w * s for w, s in zip(weights, cell)) / total) for cell in self.scores
        )

    def rank(self, score, settings):
        """The share of Manhattan (0-100) that scores lower than `score` with
        the same category weights."""
        weights = tuple(settings[c]["weight"] for c in self.categories)
        totals = self._sorted_totals(weights)
        lower = bisect.bisect_left(totals, score)
        return round(100 * lower / len(totals))
