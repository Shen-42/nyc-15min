// Map settings and the land of the five boroughs (card 15).
//
// boroughs.json holds each borough's land as [latitude, longitude] outlines,
// one per piece of land, cut to the shoreline. It's a copy of
// server/geo/boroughs.json, made by server/scripts/make_boroughs.py from the
// NYC Department of City Planning's borough boundaries. If you change one,
// copy it over.
import data from "./boroughs.json";

// The map opens on Manhattan.
export const CITY_CENTER = [40.7831, -73.9712];

// The map can't be panned past this box around the city: [south-west, north-east].
export const CITY_BOUNDS = [
  [40.45, -74.3],
  [40.97, -73.65],
];

// A big box around the city. The mask is this box with the five boroughs cut out.
export const OUTER_RING = [
  [40.3, -74.5],
  [40.3, -73.5],
  [41.1, -73.5],
  [41.1, -74.5],
];

function boundsOf(rings) {
  let south = Infinity, west = Infinity, north = -Infinity, east = -Infinity;
  for (const ring of rings) {
    for (const [lat, lng] of ring) {
      south = Math.min(south, lat);
      north = Math.max(north, lat);
      west = Math.min(west, lng);
      east = Math.max(east, lng);
    }
  }
  return [
    [south, west],
    [north, east],
  ];
}

// The boroughs in the order the picker lists them. slug names their grid files.
export const BOROUGHS = ["Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"].map((name) => ({
  name,
  slug: name.toLowerCase().replace(" ", "-"),
  rings: data.boroughs[name],
  // The main piece of land (listed first, biggest first), for the picker to fly to.
  bounds: boundsOf([data.boroughs[name][0]]),
  // Every piece, for deciding which grid files the view needs.
  allBounds: boundsOf(data.boroughs[name]),
}));

// Every piece of land, for the mask and for cutting the heat map to the shoreline.
export const LAND_POLYGONS = BOROUGHS.flatMap((b) => b.rings);

// Ray casting: draw a line from the point going east and count how many
// polygon edges it crosses. An odd count means the point is inside.
export function isInsidePolygon([lat, lng], polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [latI, lngI] = polygon[i];
    const [latJ, lngJ] = polygon[j];
    const crossesLat = latI > lat !== latJ > lat;
    if (crossesLat) {
      const lngAtLat = lngI + ((lat - latI) / (latJ - latI)) * (lngJ - lngI);
      if (lng < lngAtLat) inside = !inside;
    }
  }
  return inside;
}

// The borough a point is in, or null for water and anywhere outside the city.
export function boroughAt(point) {
  return BOROUGHS.find((b) => b.rings.some((ring) => isInsidePolygon(point, ring))) ?? null;
}

export function isInCity(point) {
  return boroughAt(point) !== null;
}

// Do two [[south, west], [north, east]] boxes overlap?
export function boxesOverlap([[s1, w1], [n1, e1]], [[s2, w2], [n2, e2]]) {
  return s1 <= n2 && s2 <= n1 && w1 <= e2 && w2 <= e1;
}
