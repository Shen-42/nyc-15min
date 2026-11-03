from shared_cache import EXPIRE_DAYS, SharedCache


class FakeRedis:
    """Just enough of a Redis client for SharedCache: get and set with an expiry."""

    def __init__(self):
        self.values, self.expiry = {}, {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex=None):
        self.values[key] = value
        self.expiry[key] = ex


class BrokenRedis:
    def get(self, key):
        raise ConnectionError("Redis is down")

    def set(self, key, value, ex=None):
        raise ConnectionError("Redis is down")


AREA = {"type": "Polygon", "coordinates": [[[-73.99, 40.75], [-73.98, 40.75], [-73.98, 40.76], [-73.99, 40.75]]]}


def test_saves_and_returns_an_area():
    redis = FakeRedis()
    cache = SharedCache(redis, "2026-11-01")
    assert cache.get("walk:15.0:42") is None
    cache.set("walk:15.0:42", AREA)
    assert cache.get("walk:15.0:42") == AREA
    assert (cache.hits, cache.misses) == (1, 1)


def test_areas_are_gzipped_and_expire():
    redis = FakeRedis()
    SharedCache(redis, "v1").set("walk:15.0:42", AREA)
    [(key, value)] = redis.values.items()
    assert value[:2] == b"\x1f\x8b"  # the gzip header
    assert redis.expiry[key] == EXPIRE_DAYS * 24 * 3600


def test_new_data_never_gets_old_areas():
    redis = FakeRedis()
    SharedCache(redis, "2026-10-01").set("walk:15.0:42", AREA)
    assert SharedCache(redis, "2026-11-01").get("walk:15.0:42") is None


def test_redis_down_means_no_cache_not_an_error(capsys):
    cache = SharedCache(BrokenRedis(), "v1")
    assert cache.get("walk:15.0:42") is None
    cache.set("walk:15.0:42", AREA)  # doesn't raise
    assert capsys.readouterr().out.count("unavailable") == 1  # warned once, not twice
