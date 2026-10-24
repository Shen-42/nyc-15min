"""Turn the result of the 15-minute search into a shape to draw on the map.

Every street segment the search reached is drawn as a line, and each line is
widened by BUFFER_M on both sides. Joined together, they cover the streets
you can walk on plus the buildings along them. The result is then trimmed to
Manhattan's shoreline with lakes and ponds cut out, so it never covers water.
"""

import json
import math
from pathlib import Path

import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

# How far on each side of a street the shape extends. 40 m covers the
# buildings along a street and fills in a normal Manhattan block from both sides.
BUFFER_M = 40

# Straighten the outline to within this many meters, to send fewer points.
SIMPLIFY_M = 5

# Points used to round each corner of a widened street (per quarter circle).
# 2 is enough at street scale and keeps the shape light to build and send.
QUAD_SEGS = 2

M_PER_DEG_LAT = 110_540

# Pieces of land in manhattan-boundary.json to trim the area to. Same as
# LAND in scripts/build_graph.py and MANHATTAN_POLYGONS on the client.
LAND = ["main", "roosevelt"]


def load_land(path):
    """Manhattan's shoreline as one shape in (lng, lat), for trimming the area.

    server/data/manhattan-boundary.json is a copy of
    client/src/data/manhattan-boundary.json. If you change one, copy it over.
    """
    data = json.loads(Path(path).read_text())
    polygons = [Polygon([(lng, lat) for lat, lng in data[name]]) for name in LAND]
    # make_valid fixes any tiny self-crossings left by simplifying the outline.
    return shapely.make_valid(unary_union(polygons))


def load_water(path):
    """Lakes and ponds inside Manhattan as a list of (name or None, shape in (lng, lat))."""
    items = json.loads(Path(path).read_text())
    return [(w["name"], shapely.make_valid(shape(w["geometry"]))) for w in items]


def walking_area(graph, start, times, max_minutes, speed_m_per_min, land=None):
    """GeoJSON geometry of everywhere reachable within max_minutes.

    times: {node_id: minutes} from WalkGraph.reachable_within.
    land: if given, the area is trimmed to it, so the 40 m widening along a
    path by a river or lake doesn't spill over the water. Pass Manhattan's
    shoreline with lakes and ponds already cut out.
    """
    # Work in meters around the start point, so buffering by 40 means 40 m.
    lat0, lng0 = graph.coords[start]
    m_per_deg_lng = 111_320 * math.cos(math.radians(lat0))

    def to_xy(point):
        lat, lng = point
        return ((lng - lng0) * m_per_deg_lng, (lat - lat0) * M_PER_DEG_LAT)

    def path_xy(u, v):
        return [to_xy(p) for p in graph.edge_points(u, v)]

    segments = []
    done = set()
    for u, t in times.items():
        for v, length_m in graph.neighbors(u):
            if v in times:
                # Both ends reached: draw the whole path, once.
                key = (min(u, v), max(u, v))
                if key in done:
                    continue
                done.add(key)
                segments.append(path_xy(u, v))
            else:
                # Only u reached: draw as far toward v as the time left allows.
                meters_left = (max_minutes - t) * speed_m_per_min
                if meters_left <= 0 or length_m <= 0:
                    continue
                segments.append(cut_path(path_xy(u, v), min(meters_left / length_m, 1.0)))

    segments = [s for s in segments if len(s) >= 2 and s[0] != s[-1]]
    if segments:
        # Widen each segment on its own, then merge them all at once.
        # Buffering one big MultiLineString does the same thing but is much
        # slower, because it works out every crossing between segments first.
        widened = shapely.buffer([LineString(s) for s in segments], BUFFER_M, quad_segs=QUAD_SEGS)
        lines = shapely.union_all(widened)
    else:
        lines = Point(0, 0).buffer(BUFFER_M, quad_segs=QUAD_SEGS)

    lines = fill_holes(lines).simplify(SIMPLIFY_M)

    # Back from meters to longitude/latitude, the order GeoJSON uses.
    def to_lnglat(xy):
        out = xy.copy()
        out[:, 0] = lng0 + xy[:, 0] / m_per_deg_lng
        out[:, 1] = lat0 + xy[:, 1] / M_PER_DEG_LAT
        return out

    area = shapely.transform(lines, to_lnglat)
    if land is not None:
        # Cut the shoreline down to the area's bounding box first, so the
        # final step only compares the area with the nearby shoreline.
        nearby_land = land.intersection(box(*area.bounds))
        area = polygons_only(area.intersection(nearby_land))
    return mapping(area)


def fill_holes(geom):
    """Fill every hole: block interiors, lawns, plazas.

    Lakes and rivers are removed afterwards by trimming to `land`, so a hole
    filled here is never water.
    """
    polygons = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    filled = [Polygon(p.exterior) for p in polygons]
    return filled[0] if len(filled) == 1 else MultiPolygon(filled)


def polygons_only(geom):
    """Trimming can leave stray lines or points where edges touch. Keep the areas."""
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if g.geom_type in ("Polygon", "MultiPolygon")]
    return unary_union(parts) if parts else Polygon()


def cut_path(points, fraction):
    """The first `fraction` (0 to 1) of a path, measured along its length."""
    pieces = [math.dist(a, b) for a, b in zip(points, points[1:])]
    target = sum(pieces) * fraction
    out = [points[0]]
    for (a, b), piece in zip(zip(points, points[1:]), pieces):
        if piece >= target:
            f = target / piece if piece else 0
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            return out
        out.append(b)
        target -= piece
    return out
