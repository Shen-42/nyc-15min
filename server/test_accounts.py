"""Tests for accounts, roles, and their edge cases (card 13).

Tokens are signed with a key made here, standing in for Supabase's, and data
is kept in memory, so these run without a Supabase project.
"""

import time
import uuid

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

import accounts
import main
from auth import SupabaseAuth
from scoring import CATEGORY_SETTINGS
from store import MAX_PLACES, MemoryStore

URL = "https://test.supabase.co"
KEY = ec.generate_private_key(ec.SECP256R1())
STRANGER_KEY = ec.generate_private_key(ec.SECP256R1())
ALICE, BOB, ADMIN = (str(uuid.uuid4()) for _ in range(3))
WEIGHTS = {c: s["weight"] for c, s in CATEGORY_SETTINGS.items()}
HOME = {"name": "Home", "lat": 40.7831, "lng": -73.9712}


def token(user, key=KEY, expires_in=3600, issuer=f"{URL}/auth/v1"):
    claims = {
        "sub": user,
        "email": f"{user[:6]}@example.com",
        "aud": "authenticated",
        "role": "authenticated",
        "iss": issuer,
        "exp": int(time.time()) + expires_in,
    }
    return jwt.encode(claims, key, algorithm="ES256")


def signed_in(user, **kwargs):
    return {"Authorization": f"Bearer {token(user, **kwargs)}"}


@pytest.fixture
def client(monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(accounts, "auth", SupabaseAuth(URL, "unused", key_for=lambda t: KEY.public_key()))
    monkeypatch.setattr(accounts, "store", store)
    monkeypatch.setattr(accounts, "admin_ids", {ADMIN})
    monkeypatch.setattr(accounts, "rate_check", None)
    monkeypatch.setitem(accounts.github, "token", None)
    c = TestClient(main.app)  # without "with": skips loading the map data
    c.store = store
    return c


# ---- Signing in ----


def test_no_token_is_refused(client):
    res = client.get("/api/saved-places")
    assert res.status_code == 401 and res.json()["detail"] == "Sign in to continue."


def test_token_signed_by_someone_else_is_refused(client):
    assert client.get("/api/me", headers=signed_in(ALICE, key=STRANGER_KEY)).status_code == 401


def test_token_for_another_project_is_refused(client):
    headers = signed_in(ALICE, issuer="https://other.supabase.co/auth/v1")
    assert client.get("/api/me", headers=headers).status_code == 401


def test_session_that_expired_mid_visit_says_so(client):
    res = client.post("/api/saved-places", json=HOME, headers=signed_in(ALICE, expires_in=-60))
    assert res.status_code == 401 and "expired" in res.json()["detail"]
    assert client.store.places == {}


def test_garbage_token_is_refused(client):
    assert client.get("/api/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_accounts_off_without_supabase(client, monkeypatch):
    monkeypatch.setattr(accounts, "auth", None)
    assert client.get("/api/me", headers=signed_in(ALICE)).status_code == 503


# ---- Saved places ----


def test_save_list_and_remove_a_place(client):
    added = client.post("/api/saved-places", json=HOME, headers=signed_in(ALICE))
    assert added.status_code == 201 and added.json()["name"] == "Home"
    listed = client.get("/api/saved-places", headers=signed_in(ALICE)).json()["places"]
    assert [p["name"] for p in listed] == ["Home"]
    removed = client.delete(f"/api/saved-places/{added.json()['id']}", headers=signed_in(ALICE))
    assert removed.status_code == 204
    assert client.get("/api/saved-places", headers=signed_in(ALICE)).json()["places"] == []


def test_users_only_see_and_remove_their_own_places(client):
    place = client.post("/api/saved-places", json=HOME, headers=signed_in(ALICE)).json()
    assert client.get("/api/saved-places", headers=signed_in(BOB)).json()["places"] == []
    assert client.delete(f"/api/saved-places/{place['id']}", headers=signed_in(BOB)).status_code == 404
    assert place["id"] in client.store.places  # still there


@pytest.mark.parametrize(
    "body",
    [
        {**HOME, "name": "   "},  # blank
        {**HOME, "name": "x" * 61},  # too long
        {**HOME, "lat": 41.5},  # far outside Manhattan
    ],
)
def test_bad_places_are_refused_with_a_message(client, body):
    res = client.post("/api/saved-places", json=body, headers=signed_in(ALICE))
    assert res.status_code == 422 and isinstance(res.json()["detail"], str)


def test_place_limit(client):
    for i in range(MAX_PLACES):
        client.store.add_place(ALICE, f"Spot {i}", 40.78, -73.97)
    res = client.post("/api/saved-places", json=HOME, headers=signed_in(ALICE))
    assert res.status_code == 422 and str(MAX_PLACES) in res.json()["detail"]


def test_removing_a_made_up_id_is_a_404(client):
    assert client.delete("/api/saved-places/not-an-id", headers=signed_in(ALICE)).status_code == 404


# ---- Needs profile ----


def test_profile_round_trip(client):
    assert client.get("/api/profile", headers=signed_in(ALICE)).json()["profile"] is None
    saved = client.put("/api/profile", json={"weights": WEIGHTS, "mode": "wheelchair", "version": 0}, headers=signed_in(ALICE))
    assert saved.status_code == 200 and saved.json()["profile"]["version"] == 1
    loaded = client.get("/api/profile", headers=signed_in(ALICE)).json()["profile"]
    assert loaded["mode"] == "wheelchair" and loaded["weights"] == WEIGHTS


def test_two_tabs_editing_the_same_profile(client):
    # Both tabs loaded version 1. Tab A saves first; tab B's save is refused
    # with the latest profile, instead of silently overwriting A's change.
    client.put("/api/profile", json={"weights": WEIGHTS, "version": 0}, headers=signed_in(ALICE))
    tab_a = client.put("/api/profile", json={"weights": {**WEIGHTS, "park": 3}, "version": 1}, headers=signed_in(ALICE))
    assert tab_a.status_code == 200 and tab_a.json()["profile"]["version"] == 2
    tab_b = client.put("/api/profile", json={"weights": {**WEIGHTS, "school": 0}, "version": 1}, headers=signed_in(ALICE))
    assert tab_b.status_code == 409
    assert tab_b.json()["profile"]["weights"]["park"] == 3


def test_bad_profiles_are_refused(client):
    for weights in ({**WEIGHTS, "bakery": 1}, {**WEIGHTS, "park": 7}, {c: 0 for c in WEIGHTS}):
        res = client.put("/api/profile", json={"weights": weights, "version": 0}, headers=signed_in(ALICE))
        assert res.status_code == 422 and isinstance(res.json()["detail"], str)


# ---- Deleting an account ----


def test_deleting_an_account_removes_all_its_data(client):
    client.post("/api/saved-places", json=HOME, headers=signed_in(ALICE))
    client.put("/api/profile", json={"weights": WEIGHTS, "version": 0}, headers=signed_in(ALICE))
    bob_place = client.post("/api/saved-places", json=HOME, headers=signed_in(BOB)).json()
    assert client.delete("/api/account", headers=signed_in(ALICE)).status_code == 204
    assert client.store.deleted_users == [ALICE]
    assert client.store.get_profile(ALICE) is None
    assert client.store.list_places(ALICE) == []
    assert bob_place["id"] in client.store.places  # other people's data stays


# ---- Roles ----


def test_me_reports_the_role(client):
    assert client.get("/api/me", headers=signed_in(ALICE)).json()["role"] == "user"
    assert client.get("/api/me", headers=signed_in(ADMIN)).json()["role"] == "admin"


@pytest.mark.parametrize("method, path", [("GET", "/api/admin/usage"), ("POST", "/api/admin/refresh")])
def test_admin_routes_are_refused_to_users(client, method, path):
    assert client.request(method, path, headers=signed_in(ALICE)).status_code == 403
    assert client.request(method, path).status_code == 401


def test_admin_sees_usage(client):
    res = client.get("/api/admin/usage", headers=signed_in(ADMIN))
    assert res.status_code == 200 and set(res.json()["totals"]) == {"profiles", "saved_places"}


def test_admin_refresh_needs_a_token_on_the_server(client):
    assert client.post("/api/admin/refresh", headers=signed_in(ADMIN)).status_code == 503


def test_admin_refresh_starts_the_workflow(client, monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return httpx.Response(204)

    monkeypatch.setitem(accounts.github, "token", "test-token")
    monkeypatch.setattr(accounts.httpx, "post", fake_post)
    res = client.post("/api/admin/refresh", headers=signed_in(ADMIN))
    assert res.status_code == 200 and res.json()["started"]
    assert calls == ["https://api.github.com/repos/Shen-42/nyc-15min/actions/workflows/refresh-data.yml/dispatches"]
