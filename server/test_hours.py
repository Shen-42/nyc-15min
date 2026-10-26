from datetime import datetime

import pytest

from hours import NYC, parse_at, status_at

# Monday, October 26, 2026
MONDAY_10AM = datetime(2026, 10, 26, 10, 0, tzinfo=NYC)
MONDAY_11PM = datetime(2026, 10, 26, 23, 0, tzinfo=NYC)
SUNDAY_10AM = datetime(2026, 10, 25, 10, 0, tzinfo=NYC)


def shop(hours, category="grocery"):
    return {"category": category, "hours": hours}


def test_parse_at_reads_new_york_time():
    at = parse_at("2026-10-26T21:00")
    assert (at.hour, at.minute, at.tzinfo) == (21, 0, NYC)


@pytest.mark.parametrize("bad", ["9pm", "2026-10-26", "2026-13-01T10:00", "2026-10-26T25:00"])
def test_parse_at_rejects_other_formats(bad):
    with pytest.raises(ValueError):
        parse_at(bad)


def test_open_and_closed_by_time_and_day():
    hours = shop("Mo-Sa 08:00-22:00")
    assert status_at(hours, MONDAY_10AM) == "open"
    assert status_at(hours, MONDAY_11PM) == "closed"
    assert status_at(hours, SUNDAY_10AM) == "closed"


def test_open_all_night():
    assert status_at(shop("24/7"), MONDAY_11PM) == "open"


def test_no_hours_or_unreadable_hours_are_unknown():
    assert status_at({"category": "pharmacy"}, MONDAY_10AM) == "unknown"
    assert status_at(shop("whenever the owner feels like it"), MONDAY_10AM) == "unknown"


def test_subway_and_schools_are_always_counted():
    assert status_at({"category": "subway"}, MONDAY_11PM) == "open"
    assert status_at(shop("Mo-Fr 08:00-15:00", "school"), MONDAY_11PM) == "open"
