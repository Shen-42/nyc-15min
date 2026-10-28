from datetime import date

from usage import MemoryUsage, Usage


def test_counts_by_day_and_route():
    today = [date(2026, 10, 28)]
    usage = Usage(MemoryUsage(), today=lambda: today[0])
    usage.hit("/api/places")
    usage.hit("/api/places")
    usage.hit("/api/area")
    today[0] = date(2026, 10, 29)
    usage.hit("/api/places")
    recent = usage.recent(2)
    assert recent[0] == {"date": "2026-10-29", "counts": {"/api/places": 1}}
    assert recent[1] == {"date": "2026-10-28", "counts": {"/api/places": 2, "/api/area": 1}}


def test_a_broken_counter_never_fails_a_request():
    class Broken:
        def hit(self, route, day):
            raise ConnectionError("Redis is down")

        def day(self, day):
            raise ConnectionError("Redis is down")

    usage = Usage(Broken())
    usage.hit("/api/places")  # no exception
    assert usage.recent(1)[0]["counts"] == {}
