"""Score a point from the places a 15-minute walk reaches (card 6).

For each category, the k nearest places earn points that fall with walking
time, and the categories are combined into a weighted 0-100 score.

    f(t)  = 1 if t <= 3 minutes, else exp(-(t - 3)^2 / 36)
    S_c   = sum of depth_i * f(t_i) over the k nearest places in category c
    score = 100 * sum(w_c * S_c) / sum(w_c)

The bell-shaped decay follows Yang et al. (2023), who scored Shanghai's
15-minute life circles at the same 80 m/min pace. Counting several places
per category follows Walk Score, which counts up to 10 restaurants.

Both published methods give full points up to 5 minutes. In Manhattan that
scored almost every point 97-99, so this version is stricter: full points
up to 3 minutes (50% at 8, 2% at 15) and more places counted per category.
On 150 random points the median is 78, with 10% below 48 and 10% above 93.
"""

import math

FULL_POINTS_MINUTES = 3
DECAY_WIDTH = 36  # 2 * sigma^2, chosen so f(8 minutes) is about 0.5
MAX_MINUTES = 15

# weight: how much the category counts toward the overall score.
#   Grocery 3 comes from Walk Score; the rest are our own choices (card 9
#   lets users change them).
# depth: how much the 1st, 2nd, 3rd nearest place counts. Each list sums to 1.
CATEGORY_SETTINGS = {
    "grocery": {"weight": 3, "depth": [0.35, 0.25, 0.2, 0.12, 0.08]},
    "subway": {"weight": 2, "depth": [0.5, 0.3, 0.2]},
    "pharmacy": {"weight": 1, "depth": [0.6, 0.25, 0.15]},
    "clinic": {"weight": 1, "depth": [0.7, 0.3]},
    "park": {"weight": 1, "depth": [0.7, 0.3]},
    "school": {"weight": 1, "depth": [0.7, 0.3]},
}


def decay(minutes):
    """Share of full points (0 to 1) for a place this many minutes away."""
    if minutes <= FULL_POINTS_MINUTES:
        return 1.0
    return math.exp(-((minutes - FULL_POINTS_MINUTES) ** 2) / DECAY_WIDTH)


def category_score(minutes_sorted, depth):
    """0 to 1 for one category, from the walking times to its places, closest first.

    Missing places (fewer than len(depth)) earn nothing.
    """
    return sum(d * decay(t) for d, t in zip(depth, minutes_sorted))


def score_walk(reached, settings=CATEGORY_SETTINGS):
    """The overall score for one point.

    reached: places the walk reaches, each with "category", "name", and
    "minutes" (the list amenities.reachable_amenities returns).
    """
    by_category = {c: [] for c in settings}
    for place in sorted(reached, key=lambda p: p["minutes"]):
        if place["category"] in by_category:
            by_category[place["category"]].append(place)

    categories = []
    weighted_sum = 0.0
    total_weight = 0.0
    nearest_times = []
    for category, s in settings.items():
        places = by_category[category]
        sub = category_score([p["minutes"] for p in places], s["depth"])
        weighted_sum += s["weight"] * sub
        total_weight += s["weight"]
        nearest_times.append(places[0]["minutes"] if places else MAX_MINUTES)
        categories.append({
            "category": category,
            "score": round(100 * sub),
            "weight": s["weight"],
            "count": len(places),
            "nearest": [
                {"name": p["name"], "minutes": p["minutes"]}
                for p in places[: len(s["depth"])]
            ],
        })

    return {
        "score": round(100 * weighted_sum / total_weight),
        # Average minutes to the nearest place in each category, adapted from
        # Bruno et al. (2024). A category with nothing in reach counts as 15.
        "proximity_minutes": round(sum(nearest_times) / len(nearest_times), 1),
        "missing": [c["category"] for c in categories if c["count"] == 0],
        "categories": categories,
    }
