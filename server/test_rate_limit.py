import pytest

from rate_limit import WINDOW_SECONDS, MemoryCounter, RateLimited, RateLimiter, RedisCounter


class FakeClock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def test_retry_after_counts_down_to_the_next_minute():
    clock = FakeClock(1_000 * WINDOW_SECONDS + 15)  # 15 seconds into a minute
    limiter = RateLimiter(2, MemoryCounter(), clock)
    limiter.check("a")
    limiter.check("a")
    with pytest.raises(RateLimited) as err:
        limiter.check("a")
    assert err.value.retry_after == 45


def test_a_new_minute_starts_fresh():
    clock = FakeClock(1_000 * WINDOW_SECONDS + 59)
    limiter = RateLimiter(1, MemoryCounter(), clock)
    limiter.check("a")
    clock.now += 2  # the next minute
    limiter.check("a")


class FakeRedis:
    """Just enough of a Redis client for RedisCounter: a pipeline with incr and expire."""

    def __init__(self):
        self.values, self.expiry = {}, {}

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis):
        self.redis, self.ops = redis, []

    def incr(self, key):
        self.ops.append(("incr", key))

    def expire(self, key, seconds):
        self.ops.append(("expire", key, seconds))

    def execute(self):
        results = []
        for op in self.ops:
            if op[0] == "incr":
                self.redis.values[op[1]] = self.redis.values.get(op[1], 0) + 1
                results.append(self.redis.values[op[1]])
            else:
                self.redis.expiry[op[1]] = op[2]
                results.append(True)
        return results


def test_redis_counter_counts_and_sets_an_expiry():
    redis = FakeRedis()
    limiter = RateLimiter(1, RedisCounter(redis), FakeClock(7 * WINDOW_SECONDS))
    limiter.check("a")
    with pytest.raises(RateLimited):
        limiter.check("a")
    assert list(redis.values.values()) == [2]
    assert list(redis.expiry.values()) == [WINDOW_SECONDS + 5]


def test_a_broken_counter_lets_searches_through():
    class Broken:
        def hit(self, key, window):
            raise ConnectionError("redis is down")

    RateLimiter(1, Broken()).check("a")  # no exception
