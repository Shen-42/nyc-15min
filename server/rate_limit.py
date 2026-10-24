"""Per-visitor rate limit for searches (card 8).

Counts each visitor's searches in fixed one-minute windows. Over the limit,
the request gets a 429 with a Retry-After header saying how many seconds
until the next window starts.

Where the counts live:
- With REDIS_URL set (on Render: the free Key Value instance in render.yaml),
  counts are kept in Redis. They survive the API sleeping and restarting,
  and would be shared if the API ever ran on more than one server.
- Without it (local development, tests), counts are kept in this process's
  memory.

If Redis can't be reached, searches are allowed rather than refused: a
broken counter shouldn't take the whole site down.
"""

import math
import os
import time

WINDOW_SECONDS = 60


class RateLimited(Exception):
    def __init__(self, retry_after):
        self.retry_after = retry_after


class MemoryCounter:
    """Counts kept in a dict. Lost when the process restarts."""

    def __init__(self):
        self.counts = {}  # (key, window number) -> count

    def hit(self, key, window):
        self.counts[(key, window)] = self.counts.get((key, window), 0) + 1
        # Drop finished windows so the dict doesn't grow forever.
        if len(self.counts) > 10_000:
            self.counts = {k: v for k, v in self.counts.items() if k[1] >= window}
        return self.counts[(key, window)]

    def clear(self):
        self.counts.clear()


class RedisCounter:
    """Counts kept in Redis: one key per visitor per minute, deleted after it ends."""

    def __init__(self, client):
        self.client = client

    def hit(self, key, window):
        redis_key = f"ratelimit:{key}:{window}"
        pipe = self.client.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        count, _ = pipe.execute()
        return count


class RateLimiter:
    def __init__(self, limit, counter, clock=time.time):
        self.limit = limit
        self.counter = counter
        self.clock = clock

    def check(self, key):
        """Count one search for `key`. Raises RateLimited if it's over the limit."""
        now = self.clock()
        window = int(now // WINDOW_SECONDS)
        try:
            count = self.counter.hit(key, window)
        except Exception as err:  # Redis down or unreachable
            print(f"Rate limit counter failed, allowing request: {err}")
            return
        if count > self.limit:
            seconds_left = (window + 1) * WINDOW_SECONDS - now
            raise RateLimited(max(1, math.ceil(seconds_left)))


def make_counter():
    url = os.environ.get("REDIS_URL")
    if not url:
        return MemoryCounter()
    import redis

    client = redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
    print("Rate limit counts are stored in Redis")
    return RedisCounter(client)
