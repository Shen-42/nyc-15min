"""Accounts, saved places, needs profiles, and the admin routes (card 13).

People sign in with Supabase Auth in the browser and send their access token
with each request here. Every route below checks the token on the server
(auth.py), and every read or write is limited to the signed-in user's own
rows (store.py). Two roles:

- user: can manage only their own saved places, profile, and account.
- admin: also sees usage counts and can start the monthly data refresh.
  Admins are listed by Supabase user id in ADMIN_USER_IDS, a setting on the
  server, so no one can make themselves an admin from the browser.

Environment settings (on Render, under the API's Environment page):
  SUPABASE_URL          https://<project>.supabase.co
  SUPABASE_SECRET_KEY   the project's secret key (never sent to the browser)
  ADMIN_USER_IDS        comma-separated user ids
  GH_REFRESH_TOKEN      a GitHub token allowed to run this repo's Actions
  GH_REPO               owner/repo, default Shen-42/nyc-15min
Without SUPABASE_URL and SUPABASE_SECRET_KEY, the routes answer 503 and the
rest of the site works as before.
"""

import os
import uuid
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import AuthError, SupabaseAuth
from modes import parse_mode
from scoring import CATEGORY_SETTINGS, MAX_IMPORTANCE
from store import MAX_PLACES, Conflict, StoreError, SupabaseStore

router = APIRouter()

# Set by setup() from the environment, or by tests.
auth = None
store = None
admin_ids = set()
usage = None
rate_check = None  # main.check_rate_limit
github = {"token": None, "repo": "Shen-42/nyc-15min", "workflow": "refresh-data.yml"}

# The same box the search routes accept.
LAT_RANGE = (40.6, 40.95)
LNG_RANGE = (-74.1, -73.85)


def setup(usage_counter, rate_limit):
    global auth, store, admin_ids, usage, rate_check
    usage = usage_counter
    rate_check = rate_limit
    admin_ids = {i.strip() for i in os.environ.get("ADMIN_USER_IDS", "").split(",") if i.strip()}
    github["token"] = os.environ.get("GH_REFRESH_TOKEN") or None
    github["repo"] = os.environ.get("GH_REPO", github["repo"])
    # Just https://<project>.supabase.co: drop a /rest/v1 or other path
    # copied from the dashboard along with it.
    url = urlsplit(os.environ.get("SUPABASE_URL", ""))
    url = f"{url.scheme}://{url.netloc}" if url.scheme and url.netloc else None
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if url and key:
        auth = SupabaseAuth(url, key)
        store = SupabaseStore(url, key)
        print(f"Accounts on: Supabase at {url}, {len(admin_ids)} admin(s)")
    else:
        print("Accounts off: set SUPABASE_URL and SUPABASE_SECRET_KEY to turn them on")


def current_user(request: Request):
    """The signed-in user, from the Authorization header. 401 if missing or invalid."""
    if auth is None or store is None:
        raise HTTPException(status_code=503, detail="Accounts aren't set up on this server.")
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    try:
        user = auth.verify(header[7:].strip())
    except AuthError as err:
        raise HTTPException(status_code=401, detail=err.message, headers={"WWW-Authenticate": "Bearer"}) from None
    user["role"] = "admin" if user["id"] in admin_ids else "user"
    if rate_check:
        rate_check(f"{user['id']}:account")
    return user


def require_admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can do this.")
    return user


def stored(call, *args):
    """Run a store call, turning Supabase outages into a readable 503."""
    try:
        return call(*args)
    except StoreError as err:
        print(err)
        raise HTTPException(status_code=503, detail="Saving isn't available right now. Try again in a minute.") from None


@router.get("/api/me")
def me(user=Depends(current_user)):
    return user


# ---- Saved places ----


class PlaceIn(BaseModel):
    name: str
    lat: float
    lng: float


@router.get("/api/saved-places")
def list_places(user=Depends(current_user)):
    return {"places": stored(store.list_places, user["id"])}


@router.post("/api/saved-places", status_code=201)
def add_place(place: PlaceIn, user=Depends(current_user)):
    name = " ".join(place.name.split())
    if not 1 <= len(name) <= 60:
        raise HTTPException(status_code=422, detail="Give the place a name of 1 to 60 characters.")
    if not (LAT_RANGE[0] <= place.lat <= LAT_RANGE[1] and LNG_RANGE[0] <= place.lng <= LNG_RANGE[1]):
        raise HTTPException(status_code=422, detail="That spot is outside Manhattan.")
    if stored(store.count_places, user["id"]) >= MAX_PLACES:
        raise HTTPException(status_code=422, detail=f"You can save up to {MAX_PLACES} places. Remove one first.")
    return stored(store.add_place, user["id"], name, round(place.lat, 6), round(place.lng, 6))


@router.delete("/api/saved-places/{place_id}", status_code=204)
def delete_place(place_id: str, user=Depends(current_user)):
    try:
        uuid.UUID(place_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="That saved place doesn't exist.") from None
    # Someone else's place looks the same as a missing one: 404, not 403,
    # so ids can't be probed.
    if not stored(store.delete_place, user["id"], place_id):
        raise HTTPException(status_code=404, detail="That saved place doesn't exist.")
    return Response(status_code=204)


# ---- Needs profile (card 9) ----


class ProfileIn(BaseModel):
    weights: dict[str, int]
    mode: str = "walk"
    # The version the browser last loaded, 0 if it has none yet.
    version: int = 0


@router.get("/api/profile")
def get_profile(user=Depends(current_user)):
    return {"profile": stored(store.get_profile, user["id"])}


@router.put("/api/profile")
def save_profile(profile: ProfileIn, user=Depends(current_user)):
    weights = profile.weights
    if set(weights) != set(CATEGORY_SETTINGS) or not all(0 <= w <= MAX_IMPORTANCE for w in weights.values()):
        raise HTTPException(status_code=422, detail="Each kind of place needs an importance from 0 to 3.")
    if not any(weights.values()):
        raise HTTPException(status_code=422, detail="Pick at least one kind of place that matters to you.")
    try:
        mode = parse_mode(profile.mode)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from None
    try:
        return {"profile": stored(store.save_profile, user["id"], weights, mode, profile.version)}
    except Conflict as conflict:
        # Another tab or device saved first. Send back what's there now.
        return JSONResponse(
            status_code=409,
            content={"detail": "Your needs were changed in another tab or device.", "profile": conflict.current},
        )


# ---- Account ----


@router.delete("/api/account", status_code=204)
def delete_account(user=Depends(current_user)):
    """Deletes the user's saved places, profile, and sign-in. Can't be undone."""
    stored(store.delete_user, user["id"])
    return Response(status_code=204)


# ---- Admin ----


@router.get("/api/admin/usage")
def admin_usage(user=Depends(require_admin)):
    return {"days": usage.recent(7) if usage else [], "totals": stored(store.stats)}


@router.post("/api/admin/refresh")
def admin_refresh(user=Depends(require_admin)):
    """Starts the monthly data refresh (card 8) now, through GitHub Actions."""
    if not github["token"]:
        raise HTTPException(status_code=503, detail="The refresh button isn't set up on this server.")
    repo, workflow = github["repo"], github["workflow"]
    try:
        res = httpx.post(
            f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches",
            headers={
                "Authorization": f"Bearer {github['token']}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"ref": "main"},
            timeout=15,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Couldn't reach GitHub. Try again in a minute.") from None
    if res.status_code != 204:
        print(f"GitHub dispatch failed: {res.status_code} {res.text[:200]}")
        raise HTTPException(status_code=502, detail=f"GitHub refused the request ({res.status_code}).")
    print(f"Data refresh started by admin {user['id']}")
    return {"started": True, "runs": f"https://github.com/{repo}/actions/workflows/{workflow}"}
