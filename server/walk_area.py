"""Turn the result of the 15-minute search into a shape to draw on the map.

Every street segment the search reached is widened by BUFFER_M on both
sides. Joined together, they cover the streets you can walk on plus the
buildings along them. The result is then trimmed to the city's shoreline
with lakes and ponds cut out, so it never covers water.

The widening is done on a grid of CELL_M squares in NumPy rather than with
shapely (card 15): mark the squares the reached streets pass through, grow
the marks by BUFFER_M, fill the holes, and turn the marked squares into one
shape. Widening each street with shapely and joining the results took about
100 ms of CPU, which is over a second on Render's free plan (a tenth of a
CPU). On the grid it takes about a sixth of that. scripts/time_area.py
compares the two.
"""

import json
import math
from pathlib import Path

import numpy as np
import shapely
from scipy import ndimage
from shapely import STRtree
from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

# How far on each side of a street the shape extends. 40 m covers the
# buildings along a street and fills in a normal Manhattan block from both sides.
BUFFER_M = 40

# Straighten the outline to within this many meters, to send fewer points.
SIMPLIFY_M = 5

# Points used to round each corner of a widened street (per quarter circle),
# for the old way of widening in scripts/time_area.py.
QUAD_SEGS = 2

M_PER_DEG_LAT = 110_540

# The grid the shape is drawn on. Measured on Nov 4 (scripts/time_area.py),
# for five spots on a laptop: 10 m squares took 65 ms in all against 427 ms
# for widening each street, and moved the outline by 1-1.4% of the area,
# a few meters along its edge. 5 m squares took 181 ms and moved it 0.6-1.1%.
CELL_M = 10

# The land of the five boroughs (card 15), made by scripts/make_boroughs.py.
BOROUGHS_FILE = Path(__file__).parent / "geo" / "boroughs.json"


def load_boroughs(path=BOROUGHS_FILE):
    """{borough name: its land as one shape in (lng, lat)}."""
    data = json.loads(Path(path).read_text())
    return {
        # make_valid fixes the tiny self-crossings left by simplifying the
        # outline. It has to run on each ring before they're joined: joining
        # fails on a ring that crosses itself.
        name: unary_union([shapely.make_valid(Polygon([(lng, lat) for lat, lng in ring])) for ring in rings])
        for name, rings in data["boroughs"].items()
    }


# Islands where nobody lives (card 15), shared with scripts/build_grid.py.
NOT_LIVED_ON_FILE = Path(__file__).parent / "geo" / "not_lived_on.json"


def load_not_lived_on(path=NOT_LIVED_ON_FILE, boroughs_path=BOROUGHS_FILE):
    """[(island name, its whole piece of land)] for each listed island: the
    ring in boroughs.json that holds the island's point."""
    islands = json.loads(Path(path).read_text())["islands"]
    rings = [ring for rings in json.loads(Path(boroughs_path).read_text())["boroughs"].values() for ring in rings]
    found = []
    for name, (lat, lng) in islands.items():
        for ring in rings:
            land = shapely.make_valid(Polygon([(x, y) for y, x in ring]))
            if land.contains(Point(lng, lat)):
                found.append((name, land))
                break
    return found


# A piece of land with fewer walking-graph nodes than this has no streets
# anyone lives on: marsh islands in Jamaica Bay, rocks off Pelham Bay.
MIN_LIVED_NODES = 10
# Land closer than this (about 20 m) to land with streets is a pier or a
# marsh joined to the shore, not an island.
TOUCH_DEGREES = 0.0002


def empty_islands(node_lat, node_lng, path=BOROUGHS_FILE, min_nodes=MIN_LIVED_NODES):
    """[(None, land)] for each island with almost no paths on it: a piece of
    a borough, other than its biggest, with fewer than min_nodes nodes and
    not touching land that has more. node_lat and node_lng are NumPy arrays
    of the walking graph's nodes."""
    with_streets, without = [], []
    for rings in json.loads(Path(path).read_text())["boroughs"].values():
        for i, ring in enumerate(rings):  # biggest first: ring 0 is the mainland
            land = shapely.make_valid(Polygon([(x, y) for y, x in ring]))
            west, south, east, north = land.bounds
            near = (node_lat >= south) & (node_lat <= north) & (node_lng >= west) & (node_lng <= east)
            count = int(shapely.contains_xy(land, node_lng[near], node_lat[near]).sum()) if near.any() else 0
            (with_streets if i == 0 or count >= min_nodes else without).append(land)
    if not without:
        return []
    lived = STRtree(with_streets)
    return [(None, land) for land in without if not len(lived.query(land, predicate="dwithin", distance=TOUCH_DEGREES))]


def load_land(path=BOROUGHS_FILE):
    """All five boroughs' land as one shape in (lng, lat), for trimming the area."""
    return shapely.make_valid(unary_union(list(load_boroughs(path).values())))


class Outlines:
    """Named shapes (lakes, parks) with a spatial index, to find quickly
    which one, if any, a point is in. The city has thousands; checking each
    one in turn would slow every click."""

    def __init__(self, items):
        self.names = [name for name, _ in items]
        self.shapes = [shape for _, shape in items]
        self.tree = STRtree(self.shapes)

    def __len__(self):
        return len(self.shapes)

    def __iter__(self):
        return iter(zip(self.names, self.shapes))

    def find(self, point):
        """(True, name or None) for the first shape containing the point, else (False, None)."""
        for i in sorted(self.tree.query(point, predicate="intersects")):
            if self.shapes[i].contains(point):
                return True, self.names[i]
        return False, None


# What to call an unnamed outline from parks.json, by its kind (card 15).
KIND_NAMES = {
    "park": "a park",
    "cemetery": "a cemetery",
    "golf course": "a golf course",
    "nature area": "a nature area",
    "airport": "an airport",
    "prison": "a prison",
}


def load_parks(path):
    """Outlines of parks and other land where nobody lives (cemeteries, golf
    courses, nature areas, airports, prisons), from scripts/build_amenities.py,
    as a list of (name, shape in (lng, lat)). Unnamed ones are called by their
    kind, e.g. "a cemetery"."""
    parks = []
    for park in json.loads(Path(path).read_text()):
        # make_valid on each ring before joining them: joining fails on a
        # ring that crosses itself, which simplifying can cause.
        rings = [shapely.make_valid(Polygon([(lng, lat) for lat, lng in ring])) for ring in park["rings"] if len(ring) >= 4]
        if rings:
            name = park["name"] or KIND_NAMES.get(park.get("kind", "park"), "a park")
            parks.append((name, unary_union(rings)))
    return parks


def load_water(path):
    """Lakes and ponds in the city as a list of (name or None, shape in (lng, lat)).
    Also reads data/waterways.json, the named rivers and bays, which has the same format."""
    items = json.loads(Path(path).read_text())
    return [(w["name"], shapely.make_valid(shape(w["geometry"]))) for w in items]


# Names that read with "the" in front: "the Hudson River", "the Arthur
# Kill", "the Kill Van Kull", but "Jamaica Bay", "Newtown Creek", "Long
# Island Sound".
THE_ENDINGS = ("River", "Canal", "Kill", "Ocean", "Channel")


class NearestName:
    """The named water nearest a click, from lines and points: the center
    lines of the big rivers and the label points of bays, which have no
    outline to be inside (card 15). A line counts within LINE_DEGREES (about
    1.3 km, more than half the Hudson's width), a label point within
    POINT_DEGREES (about 4 km, across most of Jamaica Bay)."""

    LINE_DEGREES = 0.015
    POINT_DEGREES = 0.05

    def __init__(self, items):
        self.names = [name for name, _ in items]
        self.shapes = [shape for _, shape in items]
        self.tree = STRtree(self.shapes)

    def __len__(self):
        return len(self.names)

    def find(self, point):
        """The nearest name in reach, or None."""
        best, best_distance = None, math.inf
        for i in self.tree.query(point, predicate="dwithin", distance=self.POINT_DEGREES):
            shape = self.shapes[i]
            reach = self.POINT_DEGREES if shape.geom_type in ("Point", "MultiPoint") else self.LINE_DEGREES
            distance = shape.distance(point)
            if distance <= reach and distance < best_distance:
                best, best_distance = self.names[i], distance
        return best


def water_phrase(name, lat, lng):
    """How to name the water a click landed in: "the East River", "Jamaica
    Bay". With no name, open water south of Coney Island and the Rockaways
    is the Atlantic (east of the line from Sandy Hook to Rockaway Point,
    where Lower New York Bay ends); anywhere else, "the water"."""
    if not name:
        return "the Atlantic Ocean" if lat < 40.585 and lng > -73.94 else "the water"
    if name.startswith("The "):
        return "the " + name[4:]  # "The Narrows" mid-sentence
    words = name.split()
    return f"the {name}" if words[-1] in THE_ENDINGS or words[0] == "Kill" else name


def walking_area(graph, start, times, max_minutes, speed_m_per_min, land=None, cell_m=CELL_M):
    """GeoJSON geometry of everywhere reachable within max_minutes.

    times: {node_id: minutes} from WalkGraph.reachable_within.
    land: if given, the area is trimmed to it, so the 40 m widening along a
    path by a river or lake doesn't spill over the water. Pass the city's
    shoreline with lakes and ponds already cut out.
    cell_m: the grid's square size in meters.
    """
    # Work in meters around the start point, so widening by 40 means 40 m.
    lat0, lng0 = graph.coords[start]
    m_per_deg_lng = 111_320 * math.cos(math.radians(lat0))
    points = reached_points(graph, times, max_minutes, speed_m_per_min, cell_m / 2)
    xy = np.column_stack([(points[:, 1] - lng0) * m_per_deg_lng, (points[:, 0] - lat0) * M_PER_DEG_LAT])
    xy = np.vstack([xy, [[0.0, 0.0]]])  # the start, in case nothing else was reached

    # Mark the squares the points fall in, grow the marks by BUFFER_M in
    # every direction, and fill the holes (block interiors, lawns, plazas;
    # lakes are cut out by `land` below).
    pad = BUFFER_M + 2 * cell_m
    x0, y0 = xy.min(axis=0) - pad
    x1, y1 = xy.max(axis=0) + pad
    marked = np.zeros((int((y1 - y0) // cell_m) + 1, int((x1 - x0) // cell_m) + 1), dtype=bool)
    marked[((xy[:, 1] - y0) // cell_m).astype(int), ((xy[:, 0] - x0) // cell_m).astype(int)] = True
    r = int(round(BUFFER_M / cell_m))
    dy, dx = np.mgrid[-r : r + 1, -r : r + 1]
    marked = ndimage.binary_dilation(marked, structure=dx * dx + dy * dy <= r * r)
    marked = ndimage.binary_fill_holes(marked)

    # Squares to rectangles (runs along a row, stacked while the next row
    # has the same run), then one shape. Corners are straightened to a
    # little under a square, so the outline doesn't step.
    rects = np.array(row_runs(marked), dtype=float).reshape(-1, 4) * cell_m
    joined = shapely.union_all(shapely.box(x0 + rects[:, 0], y0 + rects[:, 1], x0 + rects[:, 2], y0 + rects[:, 3]))
    lines = joined.simplify(max(SIMPLIFY_M, 0.75 * cell_m))

    # Back from meters to longitude/latitude, the order GeoJSON uses.
    def to_lnglat(coords):
        out = coords.copy()
        out[:, 0] = lng0 + coords[:, 0] / m_per_deg_lng
        out[:, 1] = lat0 + coords[:, 1] / M_PER_DEG_LAT
        return out

    area = shapely.transform(lines, to_lnglat)
    if land is not None:
        # Cut the shoreline down to the area's bounding box first, so the
        # final step only compares the area with the nearby shoreline.
        nearby_land = land.intersection(box(*area.bounds))
        area = polygons_only(area.intersection(nearby_land))
    return mapping(area)


def reached_points(graph, times, max_minutes, speed_m_per_min, step_m):
    """(lat, lng) points every step_m meters or closer along everything the
    walk reaches: whole streets between two reached corners, and the part of
    a street a walk gets along before time runs out."""
    n = len(graph.ids)
    minutes = np.full(n, np.inf)
    if times:
        minutes[np.searchsorted(graph.ids, np.fromiter(times.keys(), dtype=np.int64, count=len(times)))] = np.fromiter(
            times.values(), dtype=np.float64, count=len(times)
        )
    reached = np.isfinite(minutes)
    edges = np.flatnonzero(reached[graph.edge_a] | reached[graph.edge_b])
    if not len(edges):
        return np.empty((0, 2))
    a, b = graph.edge_a[edges], graph.edge_b[edges]

    # How far along each street the walk gets from each end, as a share of
    # its length: all of it when both ends are reached.
    length = graph.edge_length[edges]
    with np.errstate(invalid="ignore", divide="ignore"):
        share_a = np.where(reached[a], np.clip((max_minutes - minutes[a]) * speed_m_per_min / length, 0, 1), -1.0)
        share_b = np.where(reached[b], np.clip((max_minutes - minutes[b]) * speed_m_per_min / length, 0, 1), -1.0)
    both = reached[a] & reached[b]
    share_a[both | (length <= 0)] = 1.0

    # Each street's points: its start corner, the curve between, its end corner.
    curve_start = graph.shape_start[edges]
    counts = graph.shape_start[edges + 1] - curve_start + 2
    owner = np.repeat(np.arange(len(edges)), counts)
    first = np.cumsum(counts) - counts
    pos = np.arange(counts.sum()) - first[owner]
    lat = np.where(pos == 0, graph.lat[a[owner]], graph.lat[b[owner]])
    lng = np.where(pos == 0, graph.lng[a[owner]], graph.lng[b[owner]])
    middle = (pos > 0) & (pos < counts[owner] - 1)
    curve = graph.shape_points[curve_start[owner[middle]] + pos[middle] - 1]
    lat[middle], lng[middle] = curve[:, 0], curve[:, 1]

    # Pieces between consecutive points of the same street, in meters.
    m_per_deg_lng = 111_320 * math.cos(math.radians(float(lat.mean())))
    same = owner[:-1] == owner[1:]
    piece_owner = owner[:-1][same]
    ax, ay = lng[:-1][same] * m_per_deg_lng, lat[:-1][same] * M_PER_DEG_LAT
    bx, by = lng[1:][same] * m_per_deg_lng, lat[1:][same] * M_PER_DEG_LAT
    piece_m = np.hypot(bx - ax, by - ay)
    street_m = np.bincount(piece_owner, weights=piece_m, minlength=len(edges))
    before = np.cumsum(piece_m) - piece_m  # distance along all pieces to each piece's start
    before -= (np.cumsum(street_m) - street_m)[piece_owner]  # ... along its own street

    # Points along each piece, both ends included, then keep those within
    # the share of the street the walk covers from either end.
    steps = np.maximum(1, np.ceil(piece_m / step_m)).astype(int)
    which = np.repeat(np.arange(len(piece_m)), steps + 1)
    t = (np.arange(len(which)) - np.repeat(np.cumsum(steps + 1) - (steps + 1), steps + 1)) / steps[which]
    along = before[which] + t * piece_m[which]
    total = street_m[piece_owner[which]]
    with np.errstate(invalid="ignore", divide="ignore"):
        share = np.where(total > 0, along / total, 0.0)
    street = piece_owner[which]
    keep = (share <= share_a[street] + 1e-9) | (1 - share <= share_b[street] + 1e-9)
    lat_out = lat[:-1][same][which] + t * (lat[1:][same][which] - lat[:-1][same][which])
    lng_out = lng[:-1][same][which] + t * (lng[1:][same][which] - lng[:-1][same][which])
    return np.column_stack([lat_out[keep], lng_out[keep]])


def row_runs(marked):
    """Cover the True squares of a 2D array with rectangles, as
    [first column, first row, end column, end row] (ends exclusive)."""
    rects, open_runs = [], {}
    for row in range(marked.shape[0] + 1):
        runs = set()
        if row < marked.shape[0]:
            change = np.diff(np.concatenate([[0], marked[row].astype(np.int8), [0]]))
            runs = set(zip(np.flatnonzero(change == 1).tolist(), np.flatnonzero(change == -1).tolist()))
        for run in [r for r in open_runs if r not in runs]:
            rects.append([run[0], open_runs.pop(run), run[1], row])
        for run in runs:
            open_runs.setdefault(run, row)
    return rects


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
