"""Places people walk to (groceries, pharmacies, clinics, parks, schools,
subway stations), and which of them a walk reaches."""

import json
from pathlib import Path

CATEGORIES = ["grocery", "pharmacy", "clinic", "park", "school", "subway"]


def load_amenities(path):
    return json.loads(Path(path).read_text())


def reachable_amenities(amenities, times, offset=0.0):
    """Every place the walk reaches, closest first.

    times: {node_id: minutes} from WalkGraph.reachable_within.
    offset: minutes to add to every time (the walk from the click to the first node).

    A place counts as reached if any of its nodes is reached, and its time is
    the shortest one. A park can have hundreds of nodes along its paths; the
    nearest entrance is what matters.
    """
    reached = []
    for place in amenities:
        best = min((times[n] for n in place["nodes"] if n in times), default=None)
        if best is None:
            continue
        reached.append({
            "id": place["id"],
            "category": place["category"],
            "name": place["name"],
            "lat": place["lat"],
            "lng": place["lng"],
            "minutes": round(best + offset, 1),
        })
    reached.sort(key=lambda p: p["minutes"])
    return reached
