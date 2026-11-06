"""One OpenStreetMap download for every place and lake the data scripts need (card 15).

build_amenities.py and build_water.py both call download(). For the whole
city, one request per category would be about 25 pieces each (see
overpass.py); asking for every tag at once needs 25 in all. The two scripts
send the identical request, so the second one reads the first one's answer
from ./cache.
"""

import osmnx as ox

import overpass

# Every tag either script looks for. A place matches if it has any of them.
# The cemeteries, golf courses, nature reserves, wetlands, airports, and
# prisons are outlines of land where nobody lives (build_amenities.py, card 15).
# The bays and straits name the water a click lands in (build_water.py).
TAGS = {
    "shop": ["supermarket", "grocery", "greengrocer"],
    "amenity": ["pharmacy", "clinic", "doctors", "hospital", "school", "grave_yard", "prison"],
    "healthcare": "pharmacy",
    "leisure": ["park", "nature_reserve", "golf_course"],
    "railway": "station",
    "natural": ["water", "wetland", "bay", "strait"],
    "landuse": ["reservoir", "cemetery"],
    "aeroway": "aerodrome",
}

# Grow the shoreline by about 200 m so places on piers and the water's edge
# aren't cut off, and straighten it so the request stays short.
EDGE_DEGREES = 0.002
SIMPLIFY_DEGREES = 0.0005


def text(value):
    """A tag's value, or None when OpenStreetMap has none (pandas gives NaN)."""
    return value if isinstance(value, str) else None


def has_tag(row, key, values):
    """Does the row have tag key=value for any of the values?"""
    wanted = values if isinstance(values, list) else [values]
    return text(row.get(key)) in wanted


def download(land):
    """Every matching place and lake in the city, as OSMnx's GeoDataFrame."""
    area = land.buffer(EDGE_DEGREES).simplify(SIMPLIFY_DEGREES)
    features = overpass.download("places and water", lambda: ox.features_from_polygon(area, tags=TAGS))
    # A place on the line between two download pieces comes back from both.
    # Keep one, or it's saved twice and the map draws two markers for it.
    return features[~features.index.duplicated()]
