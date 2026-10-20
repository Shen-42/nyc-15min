// Map settings and the Manhattan boundary.
//
// manhattan-boundary.json holds Manhattan's shoreline as [latitude, longitude]
// points, one list per piece of land: the main island and Roosevelt Island. It comes from the NYC borough
// boundaries file in Code for Germany's "Click That 'Hood" project, simplified
// to about 2 meters of detail to keep the file small.
// Governors, Liberty, and Ellis Islands are left out because you can't walk to them.
// Marble Hill is legally Manhattan but sits on the Bronx mainland, so it's left out too.
// Randalls/Wards Island is mostly parks and sports fields, so it's left out.
import boundary from "./manhattan-boundary.json";

export const MANHATTAN_CENTER = [40.7831, -73.9712];

// The map can't be panned past this box: [south-west, north-east].
export const MANHATTAN_BOUNDS = [
  [40.68, -74.06],
  [40.89, -73.89],
];

// One outline per piece of land.
export const MANHATTAN_POLYGONS = [
  boundary.main,
  boundary.roosevelt,
];

// A big box around the city. The mask is this box with Manhattan cut out.
export const OUTER_RING = [
  [40.40, -74.40],
  [40.40, -73.60],
  [41.05, -73.60],
  [41.05, -74.40],
];

export const COMING_SOON_LABELS = [
  { name: "Brooklyn", position: [40.6950, -73.9750] },
  { name: "Queens", position: [40.7450, -73.9250] },
  { name: "The Bronx", position: [40.8450, -73.9100] },
];

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

export function isInManhattan(point) {
  return MANHATTAN_POLYGONS.some((polygon) => isInsidePolygon(point, polygon));
}
