"""Daily request counts for the admin page (card 13).

One Redis hash per day (usage:2026-10-28 -> {route: count}), kept 40 days.
In memory when Redis isn't set up. Like the rate limit, a broken counter
never fails a request.
"""

from collections import defaultdict
from datetime import date, timedelta

KEEP_DAYS = 40


class MemoryUsage:
    def __init__(self):
        self.days = defaultdict(lambda: defaultdict(int))

    def hit(self, route, day):
        self.days[day][route] += 1

    def day(self, day):
        return dict(self.days.get(day, {}))


class RedisUsage:
    def __init__(self, client):
        self.client = client

    def hit(self, route, day):
        key = f"usage:{day}"
        pipe = self.client.pipeline()
        pipe.hincrby(key, route, 1)
        pipe.expire(key, KEEP_DAYS * 86400)
        pipe.execute()

    def day(self, day):
        return {k.decode(): int(v) for k, v in self.client.hgetall(f"usage:{day}").items()}


class Usage:
    def __init__(self, backend, today=date.today):
        self.backend = backend
        self.today = today

    def hit(self, route):
        try:
            self.backend.hit(route, self.today().isoformat())
        except Exception as err:
            print(f"Usage counter failed: {err}")

    def recent(self, days=7):
        """[{"date": "2026-10-28", "counts": {route: n}}], newest first."""
        out = []
        for i in range(days):
            day = (self.today() - timedelta(days=i)).isoformat()
            try:
                counts = self.backend.day(day)
            except Exception:
                counts = {}
            out.append({"date": day, "counts": counts})
        return out


def make_usage(client):
    """client: a Redis client, or None to count in memory."""
    return Usage(MemoryUsage() if client is None else RedisUsage(client))
