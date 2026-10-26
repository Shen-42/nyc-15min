import pytest

from modes import SPEEDS, parse_mode


def test_parse_mode():
    assert parse_mode(None) == "walk"
    assert parse_mode("Wheelchair") == "wheelchair"
    with pytest.raises(ValueError):
        parse_mode("bike")


def test_wheelchair_is_slower_than_walking():
    assert SPEEDS["wheelchair"] < SPEEDS["walk"]
