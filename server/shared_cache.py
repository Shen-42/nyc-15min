"""Walking areas shared through Redis (card 15).

Drawing the shaded area is the slowest part of a search. main.py keeps
recent areas in memory, but that memory is lost every time the free API
sleeps. With REDIS_URL set (on Render: the free Key Value instance, which
stays up while the API sleeps), finished areas are also saved there, so a
spot someone searched yesterday is answered without redrawing it.

The free Key Value instance has 25 MB, shared with the rate-limit counts.
An area is gzipped to a few KB, and Redis drops the least recently used
ones when it fills up (render.yaml sets maxmemoryPolicy: allkeys-lru).

Each key includes the data version, so after the monthly refresh old areas
are never served; they expire on their own after EXPIRE_DAYS.

If Redis can't be reached, the area is just drawn again: a broken cache
shouldn't slow down or break searches.
"""

import gzip
import json
import os
import time

EXPIRE_DAYS = 30
# Print a Redis failure at most this often, so a Redis outage doesn't flood the log.
WARN_EVERY_S = 60


class SharedCache:
    def __init__(self, client, version):
        self.client = client
        self.version = version
        self.hits = 0
        self.misses = 0
        self._last_warning = None  # when the last Redis failure was printed

    def _key(self, key):
        return f"area:{self.version}:{key}"

    def get(self, key):
        """The saved value, or None if there isn't one (or Redis is down)."""
        try:
            raw = self.client.get(self._key(key))
        except Exception as err:
            self._warn(err)
            return None
        if raw is None:
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(gzip.decompress(raw))

    def set(self, key, value):
        try:
            data = gzip.compress(json.dumps(value, separators=(",", ":")).encode())
            self.client.set(self._key(key), data, ex=EXPIRE_DAYS * 24 * 3600)
        except Exception as err:
            self._warn(err)

    def _warn(self, err):
        # time.monotonic() counts from when the machine started, which can be
        # under a minute ago on a fresh server, so the first failure is always printed.
        now = time.monotonic()
        if self._last_warning is None or now - self._last_warning >= WARN_EVERY_S:
            self._last_warning = now
            print(f"Shared area cache unavailable, drawing areas again: {err}")


def make_shared_cache(version):
    """A SharedCache if REDIS_URL is set, otherwise None (local development, tests)."""
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    import redis

    client = redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
    print("Walking areas are also cached in Redis")
    return SharedCache(client, version)
