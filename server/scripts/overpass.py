"""Shared Overpass setup for the download scripts: server choice and retries.

Public Overpass servers are often busy and answer 502 "at capacity", asking
callers to retry with exponential backoff. download() does that: it retries
a request up to RETRIES times, waiting 30 s, then 1, 2, 4, and 5 minutes,
and rotates through the servers.

Which servers, in order:
- OVERPASS_URLS: a comma-separated list, if set. The refresh job sets it from
  a GitHub secret, e.g. a NextGIS server with a free key (no request limits):
      https://overpass.nextgis.com/YOUR_KEY/api,https://overpass-api.de/api
- OVERPASS_URL: one server, if set (handy when the defaults are blocked):
      OVERPASS_URL=https://overpass.kumi.systems/api python scripts/build_water.py
- Otherwise SERVERS below. The OpenStreetMap wiki lists public instances:
  https://wiki.openstreetmap.org/wiki/Overpass_API
"""

import os
import time

import osmnx as ox

# overpass-api.de is the main public server (often at capacity). VK Maps runs
# a free global mirror with no stated limits. Private.coffee, used before,
# stopped answering in 2026.
SERVERS = ["https://overpass-api.de/api", "https://maps.mail.ru/osm/tools/overpass/api"]
RETRIES = 6
FIRST_WAIT_S = 30
MAX_WAIT_S = 300


def configure():
    ox.settings.log_console = True
    # Saves each raw response in ./cache, so a rerun skips finished downloads.
    ox.settings.use_cache = True
    # Skip OSMnx's "how busy are you?" check before each request: busy servers
    # sometimes never answer it. download() handles busy servers instead.
    ox.settings.overpass_rate_limit = False
    # Give each request up to 5 minutes.
    ox.settings.requests_timeout = 300


def servers():
    listed = [u.strip() for u in os.environ.get("OVERPASS_URLS", "").split(",") if u.strip()]
    if listed:
        return listed
    chosen = os.environ.get("OVERPASS_URL")
    return [chosen] if chosen else SERVERS


def download(label, fetch):
    """Run fetch() (an OSMnx download), retrying with growing waits if the server fails."""
    choices = servers()
    for attempt in range(RETRIES):
        ox.settings.overpass_url = choices[attempt % len(choices)]
        try:
            return fetch()
        except Exception as err:
            # "Nothing matched" is an answer, not a server failure.
            if type(err).__name__ == "InsufficientResponseError":
                raise
            if attempt == RETRIES - 1:
                raise
            wait = min(FIRST_WAIT_S * 2**attempt, MAX_WAIT_S)
            host = ox.settings.overpass_url.split("/")[2]  # host only: the path may hold a key
            print(f"{label}: {host} failed ({type(err).__name__}). "
                  f"Try {attempt + 2} of {RETRIES} in {wait} s.")
            time.sleep(wait)
