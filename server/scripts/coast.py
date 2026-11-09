"""Find the creeks the borough shoreline (geo/boroughs.json) counts as land.

The Department of City Planning's shoreline runs straight across some
creeks and tidal rivers: Flushing Creek, the Hutchinson River, the marsh
channels of Jamaica Bay. OpenStreetMap has no outline for them either,
since they're part of the sea there, bounded by the coastline (lines tagged
natural=coastline). So build_water.py downloads the coastline and this
module turns it into areas of sea, then keeps the pieces of the borough
land that turn out to be sea and have a named creek running through them.

Only shapely is used, so the tests can run without OSMnx.
"""

import shapely

# A piece of land that's really sea is kept only if a named river or
# channel line runs through it this far (about 100 m). That leaves out piers
# and the thin strips where the two shorelines disagree by a few meters.
MIN_LINE_DEGREES = 0.001
# The coastline is downloaded and used this far around the city's limits
# (about 1 km), so every coastline line that crosses the limits comes whole.
FRAME_DEGREES = 0.01


def frame(city):
    """The area to download the coastline in and split into sea and land."""
    return city.buffer(FRAME_DEGREES).simplify(0.001)


def sea_areas(coast_lines, land, city):
    """The sea, as areas, from coastline pieces.

    The coastline and the edge of frame(city) split the frame into faces.
    A face is sea if most of its part inside the city's limits isn't borough
    land. Faces that are mostly outside the city (New Jersey, the rest of
    Long Island) don't matter here and count as land. If a gap in the
    coastline joins the sea to a big piece of land, the joined face is
    mostly land and counts as land: a creek is missed, not a borough."""
    # The lines aren't cut to the frame first: cut ends wouldn't sit exactly
    # on its edge. Joining them all finds the true crossings, and the parts
    # outside the frame end in the open, so they make no faces.
    noded = shapely.union_all([*coast_lines, frame(city).boundary])
    sea = []
    for face in shapely.get_parts(shapely.polygonize(shapely.get_parts(noded))):
        in_city = face.intersection(city)
        if in_city.area < 0.01 * face.area:
            continue  # outside the city
        if in_city.intersection(land).area < 0.5 * in_city.area:
            sea.append(face)
    return shapely.union_all(sea) if sea else shapely.Polygon()


def creeks_on_land(coast_lines, land, city, named_lines, min_area):
    """Pieces of `land` that the coastline says are sea, each with the name
    of the river or channel line running furthest through it.

    named_lines: (name, LineString or MultiLineString). Returns (name, shape)
    for each piece of at least min_area (in square degrees) that a line runs
    through for MIN_LINE_DEGREES or more."""
    sea = sea_areas(coast_lines, land, city)
    found = []
    for piece in shapely.get_parts(land.intersection(sea)):
        if piece.geom_type != "Polygon" or piece.area < min_area:
            continue
        best_name, best_length = None, 0.0
        for name, line in named_lines:
            if not line.intersects(piece):
                continue
            length = line.intersection(piece).length
            if length > best_length:
                best_name, best_length = name, length
        if best_length >= MIN_LINE_DEGREES:
            found.append((best_name, piece))
    return found
