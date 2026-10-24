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
