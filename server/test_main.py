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

    if not (Path(__file__).parent / "data" / "walk_graph.npz").exists():
        pytest.skip("run scripts/build_graph.py first")
    from main import rate_limiter

    rate_limiter.counter.clear()
    # "with" runs the startup code that loads the graph and places.
    with TestClient(app) as c:
        places = c.get("/api/places", params={"lat": 40.758, "lng": -73.9855})
        assert places.status_code == 200
        assert 0 <= places.json()["score"]["score"] <= 100
        assert places.json()["amenities"]
        assert places.json()["borough"] == "Manhattan"  # card 15

        area = c.get("/api/area", params={"lat": 40.758, "lng": -73.9855})
        assert area.status_code == 200
        assert area.json()["area"]["type"] in ("Polygon", "MultiPolygon")

        water = c.get("/api/places", params={"lat": 40.7855, "lng": -73.9628})  # the Reservoir
        assert water.status_code == 422

        # Card 15: rivers and the ocean are named, or at least called water.
        river = c.get("/api/places", params={"lat": 40.706, "lng": -73.996})  # under the Brooklyn Bridge
        assert river.status_code == 422
        assert river.json()["detail"].startswith("That's in the ")
        assert river.json()["detail"].endswith("Pick a spot on land.")
    rate_limiter.counter.clear()


def test_places_takes_a_needs_profile():
    from pathlib import Path

    import pytest

    if not (Path(__file__).parent / "data" / "walk_graph.npz").exists():
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

    if not (Path(__file__).parent / "data" / "walk_graph.npz").exists():
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

    if not (Path(__file__).parent / "data" / "walk_graph.npz").exists():
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


def test_rank_against_the_borough_and_the_city():
    from pathlib import Path

    import pytest

    data = Path(__file__).parent / "data"
    if not (data / "walk_graph.npz").exists() or not list(data.glob("grid-*.json")):
        pytest.skip("run scripts/build_graph.py and scripts/build_grid.py first")
    from main import rate_limiter

    rate_limiter.counter.clear()
    times_square = {"lat": 40.758, "lng": -73.9855}
    with TestClient(app) as c:
        walk = c.get("/api/places", params=times_square).json()
        rank = walk["score"]["rank"]
        assert rank["name"] == "Manhattan"
        assert 0 <= rank["borough"] <= 100 and 0 <= rank["city"] <= 100
        # Times Square has nearly everything nearby: it beats most of the city.
        assert rank["city"] > 50
        chair = c.get("/api/places", params={**times_square, "mode": "wheelchair"}).json()
        assert chair["score"]["rank"] is None
        # The grid now comes from the site's own files, not the API (card 15).
        assert c.get("/api/grid").status_code == 404
    rate_limiter.counter.clear()


def test_clicks_in_a_park_are_turned_away():
    from pathlib import Path

    import pytest

    data = Path(__file__).parent / "data"
    if not (data / "walk_graph.npz").exists() or not (data / "parks.json").exists():
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


def test_security_headers():
    res = client.get("/api/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in res.headers["content-security-policy"]


# ---- Error handling (card 14) ----


def test_unexpected_errors_get_a_plain_message_and_an_id():
    if not any(getattr(r, "path", None) == "/api/test-crash" for r in app.routes):

        @app.get("/api/test-crash")
        def crash():
            raise RuntimeError("boom")

    res = client.get("/api/test-crash")
    assert res.status_code == 500
    body = res.json()
    assert body["detail"] == "Something went wrong on our side. Try again in a minute."
    assert "boom" not in res.text  # no internals leak to the visitor
    assert body["request_id"] == res.headers["x-request-id"]
    assert res.headers["x-content-type-options"] == "nosniff"  # still gets security headers


def test_every_response_has_a_request_id():
    assert len(client.get("/api/health").headers["x-request-id"]) == 8


def test_fastapi_input_errors_are_one_readable_sentence():
    res = client.get("/api/places", params={"lat": "abc", "lng": -73.98})
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert isinstance(detail, str) and detail.startswith("Invalid lat:")
    assert res.json()["errors"][0]["loc"] == ["query", "lat"]

    missing = client.get("/api/places", params={"lng": -73.98})
    assert missing.json()["detail"].startswith("Invalid lat:")


# ---- Shared area cache (card 15) ----


def test_areas_are_saved_to_redis_and_read_back():
    from pathlib import Path

    import pytest

    import main
    from shared_cache import SharedCache
    from test_shared_cache import FakeRedis

    if not (Path(__file__).parent / "data" / "walk_graph.npz").exists():
        pytest.skip("run scripts/build_graph.py first")
    main.rate_limiter.counter.clear()
    with TestClient(app) as c:
        saved = main.shared_cache
        main.shared_cache = SharedCache(FakeRedis(), "test")
        try:
            main.cached_area.cache_clear()
            first = c.get("/api/area", params={"lat": 40.758, "lng": -73.9855})
            assert "area;" in first.headers["server-timing"]  # drawn
            main.cached_area.cache_clear()  # as if the API had slept
            second = c.get("/api/area", params={"lat": 40.758, "lng": -73.9855})
            assert "area-from-redis;" in second.headers["server-timing"]
            assert second.json() == first.json()
        finally:
            main.shared_cache = saved
            main.cached_area.cache_clear()
    main.rate_limiter.counter.clear()


def test_clicks_on_islands_where_nobody_lives_are_turned_away():
    """Card 15: Rikers, Randall's and Wards, North Brother, the marsh islands, and the rest."""
    from pathlib import Path

    import pytest

    if not (Path(__file__).parent / "data" / "walk_graph.npz").exists():
        pytest.skip("run scripts/build_graph.py first")
    from main import rate_limiter

    rate_limiter.counter.clear()
    with TestClient(app) as c:
        for lat, lng in [(40.7934, -73.8845), (40.7890, -73.9205), (40.8008, -73.8990)]:
            res = c.get("/api/places", params={"lat": lat, "lng": lng})
            assert res.status_code == 422
            assert res.json()["detail"].endswith("has no residential areas. Pick a spot where people live.")
        # Islands with no streets: a Jamaica Bay marsh, Hoffman Island, Mill Rock.
        for lat, lng in [(40.62417, -73.85296), (40.57883, -74.05367), (40.78063, -73.93785)]:
            res = c.get("/api/places", params={"lat": lat, "lng": lng})
            assert res.status_code == 422
            assert res.json()["detail"].startswith("This island has no residential areas")
        roosevelt = c.get("/api/places", params={"lat": 40.7620, "lng": -73.9497})  # people live here
        assert roosevelt.status_code == 200
    rate_limiter.counter.clear()


def test_a_click_in_a_park_suggests_the_nearest_street_outside_it():
    """Heuristic 9: "That's in Central Park" comes with a way forward."""
    from pathlib import Path

    import pytest

    data = Path(__file__).parent / "data"
    if not (data / "walk_graph.npz").exists() or not (data / "parks.json").exists():
        pytest.skip("run scripts/build_graph.py and scripts/build_amenities.py first")
    from main import rate_limiter

    rate_limiter.counter.clear()
    great_lawn = {"lat": 40.7812, "lng": -73.9665}
    with TestClient(app) as c:
        refused = c.get("/api/places", params=great_lawn)
        assert refused.status_code == 422
        assert refused.headers.get("X-Suggest") == "nearest-street"
        street = c.get("/api/nearest-street", params=great_lawn)
        assert street.status_code == 200
        spot = street.json()
        assert spot["distance_m"] < 1000
        assert c.get("/api/places", params={"lat": spot["lat"], "lng": spot["lng"]}).status_code == 200
        rikers = c.get("/api/places", params={"lat": 40.7934, "lng": -73.8845})
        assert "X-Suggest" not in rikers.headers  # its nearest street is on the island
    rate_limiter.counter.clear()
