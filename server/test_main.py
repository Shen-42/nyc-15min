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

    from main import SEARCHES_PER_MINUTE, check_rate_limit, recent_searches

    recent_searches.clear()
    for _ in range(SEARCHES_PER_MINUTE):
        check_rate_limit("203.0.113.7")
    with pytest.raises(HTTPException) as err:
        check_rate_limit("203.0.113.7")
    assert err.value.status_code == 429
    check_rate_limit("198.51.100.1")  # a different visitor is unaffected
    recent_searches.clear()


def test_places_and_area_endpoints():
    from pathlib import Path

    import pytest

    if not (Path(__file__).parent / "data" / "walk_graph.json").exists():
        pytest.skip("run scripts/build_graph.py first")
    from main import recent_searches

    recent_searches.clear()
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
    recent_searches.clear()
