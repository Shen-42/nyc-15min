"""Places people walk to (groceries, pharmacies, clinics, parks, schools,
subway stations), and which of them a walk reaches."""

import json
from pathlib import Path

import numpy as np

CATEGORIES = ["grocery", "pharmacy", "clinic", "park", "school", "subway"]


def load_amenities(path):
    return json.loads(Path(path).read_text())


class PlaceIndex:
    """Every place's graph nodes in two flat arrays, so a walk's reach is
    matched against all of them at once in NumPy (card 15). With the whole
    city's places, checking them one by one in Python took too long."""

    def __init__(self, amenities):
        self.amenities = amenities
        sizes = [len(p["nodes"]) for p in amenities]
        self.node = np.fromiter((n for p in amenities for n in p["nodes"]), dtype=np.int64, count=sum(sizes))
        self.owner = np.repeat(np.arange(len(amenities)), sizes)  # which place each node belongs to

    def reachable(self, times, offset=0.0):
        """Every place the walk reaches, closest first.

        times: {node_id: minutes} from WalkGraph.reachable_within.
        offset: minutes to add to every time (the walk from the click to the first node).

        A place counts as reached if any of its nodes is reached, and its time is
        the shortest one. A park can have hundreds of nodes along its paths; the
        nearest entrance is what matters.
        """
        if not times or not len(self.node):
            return []
        reached = np.fromiter(times.keys(), dtype=np.int64, count=len(times))
        minutes = np.fromiter(times.values(), dtype=np.float64, count=len(times))
        order = np.argsort(reached)
        reached, minutes = reached[order], minutes[order]
        at = np.minimum(np.searchsorted(reached, self.node), len(reached) - 1)
        hit = reached[at] == self.node
        best = np.full(len(self.amenities), np.inf)
        np.minimum.at(best, self.owner[hit], minutes[at[hit]])

        found = []
        for i in np.flatnonzero(np.isfinite(best)).tolist():
            place = self.amenities[i]
            found.append({
                "id": place["id"],
                "category": place["category"],
                "name": place["name"],
                "lat": place["lat"],
                "lng": place["lng"],
                "minutes": round(float(best[i]) + offset, 1),
            })
        found.sort(key=lambda p: p["minutes"])  # stable: ties keep the file's order
        return found


def reachable_amenities(amenities, times, offset=0.0):
    """Every place the walk reaches, closest first. `amenities` is a
    PlaceIndex, or a plain list of places (indexed on the spot, which is
    fine for a few, slow for the whole city)."""
    index = amenities if isinstance(amenities, PlaceIndex) else PlaceIndex(amenities)
    return index.reachable(times, offset)
