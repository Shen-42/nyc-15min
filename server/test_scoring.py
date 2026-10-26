from pathlib import Path

import pytest

from scoring import CATEGORY_SETTINGS, category_score, decay, parse_weights, score_walk, settings_with_weights


def place(category, minutes, name=None):
    return {"category": category, "minutes": minutes, "name": name}


def everything_within(minutes):
    """Enough places in every category, all this many minutes away."""
    return [place(c, minutes) for c, s in CATEGORY_SETTINGS.items() for _ in s["depth"]]


def test_decay_full_points_up_to_3_minutes():
    assert decay(0) == 1.0
    assert decay(3) == 1.0


def test_decay_half_at_8_and_almost_nothing_at_15():
    assert decay(8) == pytest.approx(0.5, abs=0.01)
    assert decay(15) == pytest.approx(0.02, abs=0.01)


def test_decay_keeps_falling():
    assert decay(6) > decay(8) > decay(12) > decay(15)


def test_category_counts_the_second_and_third_choice():
    depth = [0.6, 0.25, 0.15]
    assert category_score([1], depth) == pytest.approx(0.6)
    assert category_score([1, 2], depth) == pytest.approx(0.85)
    assert category_score([1, 2, 3], depth) == pytest.approx(1.0)
    assert category_score([], depth) == 0


def test_everything_close_scores_100():
    result = score_walk(everything_within(3))
    assert result["score"] == 100
    assert result["missing"] == []
    assert result["proximity_minutes"] == 3.0


def test_nothing_in_reach_scores_0():
    result = score_walk([])
    assert result["score"] == 0
    assert result["proximity_minutes"] == 15.0
    assert set(result["missing"]) == set(CATEGORY_SETTINGS)


def test_groceries_count_three_times_as_much_as_a_park():
    groceries_only = score_walk([place("grocery", 1)] * 5)["score"]
    park_only = score_walk([place("park", 1)] * 2)["score"]
    # Weights add up to 9: grocery is 3/9 of the score, a park 1/9.
    assert groceries_only == round(100 * 3 / 9)
    assert park_only == round(100 * 1 / 9)


def test_breakdown_lists_the_nearest_places_in_order():
    reached = [place("pharmacy", 7, "B"), place("pharmacy", 2, "A"), place("pharmacy", 9, "C"), place("pharmacy", 11, "D")]
    pharmacy = next(c for c in score_walk(reached)["categories"] if c["category"] == "pharmacy")
    assert pharmacy["count"] == 4
    assert [p["name"] for p in pharmacy["nearest"]] == ["A", "B", "C"]  # only the 3 that count


def test_parse_weights():
    assert parse_weights("grocery:3, school:0") == {"grocery": 3, "school": 0}
    assert parse_weights("") == {}
    assert parse_weights(None) == {}


@pytest.mark.parametrize("bad", ["bakery:2", "grocery:high", "grocery:4", "park:-1"])
def test_parse_weights_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        parse_weights(bad)


def test_all_weights_zero_is_refused():
    with pytest.raises(ValueError):
        settings_with_weights({c: 0 for c in CATEGORY_SETTINGS})


def test_categories_left_out_keep_their_default_weight():
    settings = settings_with_weights({"park": 3})
    assert settings["park"]["weight"] == 3
    assert settings["grocery"]["weight"] == CATEGORY_SETTINGS["grocery"]["weight"]


def test_weight_zero_leaves_a_category_out_of_score_and_proximity():
    # Everything nearby except schools, which are 14 minutes away.
    reached = [p for p in everything_within(2) if p["category"] != "school"] + [place("school", 14)]
    default = score_walk(reached)
    no_schools = score_walk(reached, settings_with_weights({"school": 0}))
    assert no_schools["score"] > default["score"]
    assert no_schools["score"] == 100
    assert no_schools["proximity_minutes"] == 2.0
    school = next(c for c in no_schools["categories"] if c["category"] == "school")
    assert school["counted"] is False and school["count"] == 1


def test_missing_lists_only_counted_categories():
    reached = [p for p in everything_within(2) if p["category"] != "school"]
    assert score_walk(reached)["missing"] == ["school"]
    assert score_walk(reached, settings_with_weights({"school": 0}))["missing"] == []


def test_closed_places_do_not_count():
    reached = everything_within(2)
    for p in reached:
        p["status"] = "open"
    open_score = score_walk(reached)["score"]
    for p in reached:
        if p["category"] == "grocery":
            p["status"] = "closed"
    result = score_walk(reached)
    grocery = next(c for c in result["categories"] if c["category"] == "grocery")
    assert result["score"] < open_score
    assert grocery["score"] == 0 and grocery["count"] == 0 and grocery["closed_count"] == 5
    assert len(grocery["closed"]) == 3
    assert "grocery" in result["missing"]


def test_unknown_hours_count_as_open():
    reached = everything_within(2)
    for p in reached:
        p["status"] = "unknown"
    assert score_walk(reached)["score"] == 100


# On the real data. Skipped until the graph and places have been built.
DATA = Path(__file__).parent / "data"
needs_data = pytest.mark.skipif(
    not ((DATA / "walk_graph.json").exists() and (DATA / "amenities.json").exists()),
    reason="run scripts/build_graph.py and scripts/build_amenities.py first",
)


def score_at(lat, lng):
    from amenities import load_amenities, reachable_amenities
    from graph import WalkGraph

    graph = WalkGraph.from_file(DATA / "walk_graph.json")
    places = load_amenities(DATA / "amenities.json")
    start, _ = graph.nearest_node(lat, lng)
    return score_walk(reachable_amenities(places, graph.reachable_within(start, 15)))


@needs_data
def test_times_square_outscores_four_freedoms_park():
    midtown = score_at(40.7580, -73.9855)
    roosevelt_tip = score_at(40.7505, -73.9614)  # southern tip of Roosevelt Island
    assert midtown["score"] >= 75
    assert midtown["score"] > roosevelt_tip["score"]
