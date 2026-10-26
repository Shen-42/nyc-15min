"""Opening hours (card 10): is a place open at a given time in New York?

Hours come from OpenStreetMap's opening_hours tag, for example
"Mo-Sa 08:00-22:00; Su 09:00-21:00". The opening-hours-py library reads them.
"""

from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from opening_hours import OpeningHours

NYC = ZoneInfo("America/New_York")

# Categories whose places open and close. The subway runs all night, and a
# school matters for being nearby, not for being open at 9 pm.
TIMED_CATEGORIES = {"grocery", "pharmacy", "clinic", "park"}


def parse_at(text):
    """Turn "2026-10-26T21:00" (New York time) into a datetime. Raises ValueError
    with a message meant for the person using the site."""
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M").replace(tzinfo=NYC)
    except ValueError:
        raise ValueError("The time must look like 2026-10-26T21:00, in New York time.") from None


@lru_cache(maxsize=None)
def parsed(hours):
    """The parsed hours, or None if OpenStreetMap has a value the library can't read.
    Cached because many places share the same hours ("24/7", "Mo-Su 07:00-23:00")."""
    try:
        return OpeningHours(hours, timezone=NYC)
    except Exception:  # the library raises its own error for bad syntax
        return None


def status_at(place, at):
    """ "open", "closed", or "unknown" for a place at a time."""
    if place["category"] not in TIMED_CATEGORIES:
        return "open"
    hours = place.get("hours")
    oh = parsed(hours) if hours else None
    if oh is None:
        return "unknown"
    if oh.is_open(at):
        return "open"
    if oh.is_closed(at):
        return "closed"
    return "unknown"  # hours OpenStreetMap itself marks as unknown, e.g. "Mo-Fr unknown"
