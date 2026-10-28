"""SupabaseStore against a fake Supabase (httpx.MockTransport): checks the
requests it sends, especially that every query is filtered by the user."""

import json

import httpx
import pytest

from store import Conflict, StoreError, SupabaseStore

URL = "https://test.supabase.co"
USER = "11111111-1111-1111-1111-111111111111"


def make_store(handler, key="sb_secret_abc"):
    seen = []

    def record(request):
        seen.append(request)
        return handler(request)

    store = SupabaseStore(URL, key, client=httpx.Client(transport=httpx.MockTransport(record)))
    return store, seen


def test_secret_key_goes_in_apikey_only():
    store, seen = make_store(lambda r: httpx.Response(200, json=[]))
    store.list_places(USER)
    assert seen[0].headers["apikey"] == "sb_secret_abc"
    assert "authorization" not in seen[0].headers
    legacy, seen = make_store(lambda r: httpx.Response(200, json=[]), key="a.b.c")
    legacy.list_places(USER)
    assert seen[0].headers["authorization"] == "Bearer a.b.c"


def test_every_query_is_filtered_by_user():
    store, seen = make_store(lambda r: httpx.Response(200, json=[]))
    store.list_places(USER)
    store.delete_place(USER, "22222222-2222-2222-2222-222222222222")
    store.get_profile(USER)
    for request in seen:
        assert request.url.params["user_id"] == f"eq.{USER}"


def test_profile_update_only_matches_the_loaded_version():
    def handler(request):
        if request.method == "PATCH":
            assert request.url.params["version"] == "eq.3"
            return httpx.Response(200, json=[])  # no row had version 3: someone saved first
        return httpx.Response(200, json=[{"weights": {}, "mode": "walk", "version": 4, "updated_at": "x"}])

    store, _ = make_store(handler)
    with pytest.raises(Conflict) as conflict:
        store.save_profile(USER, {"grocery": 3}, "walk", 3)
    assert conflict.value.current["version"] == 4


def test_first_profile_save_that_loses_a_race():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(409, json={"code": "23505"})
        return httpx.Response(200, json=[{"weights": {}, "mode": "walk", "version": 1, "updated_at": "x"}])

    store, _ = make_store(handler)
    with pytest.raises(Conflict):
        store.save_profile(USER, {"grocery": 3}, "walk", 0)


def test_profile_save_sends_the_next_version():
    def handler(request):
        body = json.loads(request.content)
        return httpx.Response(200, json=[{**body, "updated_at": "x"}])

    store, _ = make_store(handler)
    assert store.save_profile(USER, {"grocery": 3}, "walk", 1)["version"] == 2


def test_counts_come_from_the_content_range_header():
    store, _ = make_store(lambda r: httpx.Response(200, json=[], headers={"content-range": "0-0/17"}))
    assert store.count_places(USER) == 17


def test_deleting_a_user_removes_rows_then_the_sign_in():
    store, seen = make_store(lambda r: httpx.Response(200, json=[]))
    store.delete_user(USER)
    assert [(r.method, r.url.path) for r in seen] == [
        ("DELETE", "/rest/v1/saved_places"),
        ("DELETE", "/rest/v1/profiles"),
        ("DELETE", f"/auth/v1/admin/users/{USER}"),
    ]


def test_outages_become_store_errors():
    def down(request):
        raise httpx.ConnectError("down")

    store, _ = make_store(down)
    with pytest.raises(StoreError):
        store.list_places(USER)
    store, _ = make_store(lambda r: httpx.Response(500, text="oops"))
    with pytest.raises(StoreError):
        store.list_places(USER)
