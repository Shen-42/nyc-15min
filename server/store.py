"""Where saved places and needs profiles live (card 13).

SupabaseStore keeps them in two Supabase Postgres tables (see
supabase/schema.sql), reached through Supabase's REST API with the secret
key. Row-level security is on with no policies, so only this server can read
or write them; the browser's public key can't. Ownership is enforced here:
every query is filtered by the signed-in user's id.

MemoryStore keeps the same data in dicts, for tests and for running the
site locally without a Supabase project.
"""

import uuid
from datetime import datetime, timezone

import httpx

MAX_PLACES = 50


class StoreError(Exception):
    """Supabase couldn't be reached or refused the request."""


class Conflict(Exception):
    """The profile changed since the client loaded it (another tab or device)."""

    def __init__(self, current):
        self.current = current


def now():
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self):
        self.places = {}  # place id -> row
        self.profiles = {}  # user id -> row
        self.deleted_users = []

    def list_places(self, user_id):
        rows = [p for p in self.places.values() if p["user_id"] == user_id]
        return [public(p) for p in sorted(rows, key=lambda p: p["created_at"])]

    def count_places(self, user_id):
        return sum(1 for p in self.places.values() if p["user_id"] == user_id)

    def add_place(self, user_id, name, lat, lng):
        row = {"id": str(uuid.uuid4()), "user_id": user_id, "name": name, "lat": lat, "lng": lng, "created_at": now()}
        self.places[row["id"]] = row
        return public(row)

    def delete_place(self, user_id, place_id):
        row = self.places.get(place_id)
        if not row or row["user_id"] != user_id:
            return False
        del self.places[place_id]
        return True

    def get_profile(self, user_id):
        row = self.profiles.get(user_id)
        return dict(row) if row else None

    def save_profile(self, user_id, weights, mode, version):
        current = self.profiles.get(user_id)
        if (current["version"] if current else 0) != version:
            raise Conflict(dict(current) if current else None)
        row = {"weights": weights, "mode": mode, "version": version + 1, "updated_at": now()}
        self.profiles[user_id] = row
        return dict(row)

    def delete_user(self, user_id):
        self.places = {k: v for k, v in self.places.items() if v["user_id"] != user_id}
        self.profiles.pop(user_id, None)
        self.deleted_users.append(user_id)

    def stats(self):
        return {"profiles": len(self.profiles), "saved_places": len(self.places)}


def public(row):
    """A saved place as the API returns it (no user id)."""
    return {k: row[k] for k in ("id", "name", "lat", "lng", "created_at")}


class SupabaseStore:
    def __init__(self, url, secret_key, client=None):
        self.url = url.rstrip("/")
        self.headers = {"apikey": secret_key}
        # Legacy service_role keys are JWTs and go in Authorization too.
        # The newer sb_secret_ keys must not.
        if secret_key.count(".") == 2:
            self.headers["Authorization"] = f"Bearer {secret_key}"
        self.client = client or httpx.Client(timeout=10)

    def _request(self, method, path, **kwargs):
        headers = {**self.headers, **kwargs.pop("headers", {})}
        try:
            res = self.client.request(method, f"{self.url}{path}", headers=headers, **kwargs)
        except httpx.HTTPError as err:
            raise StoreError(f"Supabase unreachable: {err}") from None
        if res.status_code >= 400 and res.status_code != 409:
            raise StoreError(f"Supabase {method} {path}: {res.status_code} {res.text[:200]}")
        return res

    def _count(self, table, filters=None):
        res = self._request(
            "GET",
            f"/rest/v1/{table}",
            params={"select": "*", **(filters or {})},
            headers={"Prefer": "count=exact", "Range": "0-0"},
        )
        return int(res.headers.get("content-range", "*/0").split("/")[-1])

    def list_places(self, user_id):
        res = self._request(
            "GET",
            "/rest/v1/saved_places",
            params={"user_id": f"eq.{user_id}", "select": "id,name,lat,lng,created_at", "order": "created_at.asc"},
        )
        return res.json()

    def count_places(self, user_id):
        return self._count("saved_places", {"user_id": f"eq.{user_id}"})

    def add_place(self, user_id, name, lat, lng):
        res = self._request(
            "POST",
            "/rest/v1/saved_places",
            json={"user_id": user_id, "name": name, "lat": lat, "lng": lng},
            headers={"Prefer": "return=representation"},
        )
        return public(res.json()[0])

    def delete_place(self, user_id, place_id):
        res = self._request(
            "DELETE",
            "/rest/v1/saved_places",
            params={"id": f"eq.{place_id}", "user_id": f"eq.{user_id}"},
            headers={"Prefer": "return=representation"},
        )
        return bool(res.json())

    def get_profile(self, user_id):
        res = self._request(
            "GET",
            "/rest/v1/profiles",
            params={"user_id": f"eq.{user_id}", "select": "weights,mode,version,updated_at"},
        )
        rows = res.json()
        return rows[0] if rows else None

    def save_profile(self, user_id, weights, mode, version):
        body = {"weights": weights, "mode": mode, "version": version + 1, "updated_at": now()}
        if version == 0:
            # First save. If another tab got there first, the insert hits
            # the primary key and comes back 409.
            res = self._request(
                "POST",
                "/rest/v1/profiles",
                json={"user_id": user_id, **body},
                headers={"Prefer": "return=representation"},
            )
            if res.status_code == 409:
                raise Conflict(self.get_profile(user_id))
        else:
            # Only update the row if nobody changed it since `version`.
            res = self._request(
                "PATCH",
                "/rest/v1/profiles",
                params={"user_id": f"eq.{user_id}", "version": f"eq.{version}"},
                json=body,
                headers={"Prefer": "return=representation"},
            )
            if not res.json():
                raise Conflict(self.get_profile(user_id))
        row = res.json()[0]
        return {k: row[k] for k in ("weights", "mode", "version", "updated_at")}

    def delete_user(self, user_id):
        # The tables cascade from auth.users, but delete the rows first so
        # nothing is left behind if the account deletion fails partway.
        self._request("DELETE", "/rest/v1/saved_places", params={"user_id": f"eq.{user_id}"})
        self._request("DELETE", "/rest/v1/profiles", params={"user_id": f"eq.{user_id}"})
        self._request("DELETE", f"/auth/v1/admin/users/{user_id}")

    def stats(self):
        return {"profiles": self._count("profiles"), "saved_places": self._count("saved_places")}
