from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_rate_limit_allows_normal_use_then_says_wait():
    import pytest
    from fastapi import HTTPException

    from main import SEARCHES_PER_MINUTE, check_rate_limit, rate_limiter

    rate_limiter.counter.clear()
    for _ in range(SEARCHES_PER_MINUTE):
        check_rate_limit("203.0.113.7")
    with pytest.raises(HTTPException) as err:
        check_rate_limit("203.0.113.7")
    assert err.value.status_code == 429
    assert 1 <= int(err.value.headers["Retry-After"]) <= 60
    check_rate_limit("198.51.100.1")  # a different visitor is unaffected
    rate_limiter.counter.clear()


def test_places_and_area_endpoints():
    from pathlib import Path

    import pytest

    if not (Path(__file__).parent / "data" / "walk_graph.json").exists():
        pytest.skip("run scripts/build_graph.py first")
    from main import rate_limiter

    rate_limiter.counter.clear()
    # "with" runs the startup code that loads the graph and places.
    with TestClient(app) as c:
        places = c.get("/api/places", params={"lat": 40.758, "lng": -73.9855})
        assert places.status_code == 200
        assert 0 <= places.json()["score"]["score"] <= 100
        assert places.json()["amenities"]

        area = c.get("/api/area", params={"lat": 40.758, "lng": -73.9855})
        assert area.status_code == 200
        assert area.json()["area"]["type"] in ("Polygon", "MultiPolygon")

        water = c.get("/api/places", params={"lat": 40.7855, "lng": -73.9628})  # the Reservoir
        assert water.status_code == 422
    rate_limiter.counter.clear()


def test_places_takes_a_needs_profile():
    from pathlib import Path

    import pytest

    if not (Path(__file__).parent / "data" / "walk_graph.json").exists():
        pytest.skip("run scripts/build_graph.py first")
    from main import rate_limiter

    rate_limiter.counter.clear()
    times_square = {"lat": 40.758, "lng": -73.9855}
    with TestClient(app) as c:
        parent = c.get("/api/places", params={**times_square, "weights": "park:3,school:3,pharmacy:2,clinic:2"})
        assert parent.status_code == 200
        by_id = {cat["category"]: cat for cat in parent.json()["score"]["categories"]}
        assert by_id["park"]["weight"] == 3 and by_id["grocery"]["weight"] == 3

        no_schools = c.get("/api/places", params={**times_square, "weights": "school:0"})
        school = next(cat for cat in no_schools.json()["score"]["categories"] if cat["category"] == "school")
        assert school["counted"] is False

        for bad in ["bakery:2", "grocery:9", "grocery:3,subway:0,pharmacy:0,clinic:0,park:0,school:0,grocery:0"]:
            res = c.get("/api/places", params={**times_square, "weights": bad})
            assert res.status_code == 422
            assert isinstance(res.json()["detail"], str)
    rate_limiter.counter.clear()


def test_places_checks_opening_hours_at_a_time():
    from pathlib import Path

    import pytest

    if not (Path(__file__).parent / "data" / "walk_graph.json").exists():
        pytest.skip("run scripts/build_graph.py first")
    from main import rate_limiter

    rate_limiter.counter.clear()
    times_square = {"lat": 40.758, "lng": -73.9855}
    with TestClient(app) as c:
        anytime = c.get("/api/places", params=times_square).json()
        assert all("status" not in p for p in anytime["amenities"])

        late = c.get("/api/places", params={**times_square, "at": "2026-10-26T03:00"})
        assert late.status_code == 200
        statuses = {p["status"] for p in late.json()["amenities"]}
        assert statuses <= {"open", "closed", "unknown"}
        assert late.json()["score"]["score"] <= anytime["score"]["score"]

        bad = c.get("/api/places", params={**times_square, "at": "9pm"})
        assert bad.status_code == 422 and isinstance(bad.json()["detail"], str)
    rate_limiter.counter.clear()


def test_wheelchair_mode_reaches_less_and_rejects_unknown_modes():
    from pathlib import Path

    import pytest

    if not (Path(__file__).parent / "data" / "walk_graph.json").exists():
        pytest.skip("run scripts/build_graph.py first")
    from main import rate_limiter

    rate_limiter.counter.clear()
    times_square = {"lat": 40.758, "lng": -73.9855}
    with TestClient(app) as c:
        walk = c.get("/api/places", params=times_square).json()
        chair = c.get("/api/places", params={**times_square, "mode": "wheelchair"}).json()
        assert chair["mode"] == "wheelchair" and walk["barriers"] == []
        assert len(chair["amenities"]) < len(walk["amenities"])
        assert all({"lat", "lng", "minutes"} <= set(b) for b in chair["barriers"])

        area = c.get("/api/area", params={**times_square, "mode": "wheelchair"})
        assert area.status_code == 200

        bad = c.get("/api/places", params={**times_square, "mode": "skateboard"})
        assert bad.status_code == 422 and isinstance(bad.json()["detail"], str)
    rate_limiter.counter.clear()


def test_grid_and_rank():
    from pathlib import Path

    import pytest

    data = Path(__file__).parent / "data"
    if not (data / "walk_graph.json").exists() or not (data / "grid.json").exists():
        pytest.skip("run scripts/build_graph.py and scripts/build_grid.py first")
    from main import rate_limiter

    rate_limiter.counter.clear()
    times_square = {"lat": 40.758, "lng": -73.9855}
    with TestClient(app) as c:
        res = c.get("/api/grid")
        assert res.status_code == 200
        body = res.json()
        assert len(body["cells"]) > 4000 and set(body["gaps"]) == set(body["meta"]["categories"])

        walk = c.get("/api/places", params=times_square).json()
        assert 0 <= walk["score"]["rank"] <= 100
        chair = c.get("/api/places", params={**times_square, "mode": "wheelchair"}).json()
        assert chair["score"]["rank"] is None
    rate_limiter.counter.clear()


def test_clicks_in_a_park_are_turned_away():
    from pathlib import Path

    import pytest

    data = Path(__file__).parent / "data"
    if not (data / "walk_graph.json").exists() or not (data / "parks.json").exists():
        pytest.skip("run scripts/build_graph.py and scripts/build_amenities.py first")
    from main import rate_limiter

    rate_limiter.counter.clear()
    with TestClient(app) as c:
        sheep_meadow = c.get("/api/places", params={"lat": 40.7716, "lng": -73.9750})
        assert sheep_meadow.status_code == 422
        assert "park" in sheep_meadow.json()["detail"].lower()
        times_square = c.get("/api/places", params={"lat": 40.758, "lng": -73.9855})
        assert times_square.status_code == 200
    rate_limiter.counter.clear()
