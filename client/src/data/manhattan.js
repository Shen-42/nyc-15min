// Map settings and a rough outline of Manhattan.
// Points are [latitude, longitude], traced by hand along the shoreline.
// The outline is close enough for the "coming soon" mask and for
// rejecting clicks outside Manhattan. Swap in the official borough
// boundary from NYC Open Data later if you need it exact.

export const MANHATTAN_CENTER = [40.7831, -73.9712];

// The map can't be panned past this box: [south-west, north-east].
export const MANHATTAN_BOUNDS = [
  [40.68, -74.06],
  [40.89, -73.89],
];

export const MANHATTAN_OUTLINE = [
  // West side, Battery up the Hudson
  [40.7003, -74.0170],
  [40.7170, -74.0140],
  [40.7240, -74.0120],
  [40.7420, -74.0100],
  [40.7560, -74.0040],
  [40.7710, -73.9930],
  [40.7820, -73.9880],
  [40.7990, -73.9760],
  [40.8210, -73.9600],
  [40.8350, -73.9500],
  [40.8510, -73.9470],
  [40.8650, -73.9320],
  [40.8740, -73.9280],
  [40.8790, -73.9230], // Spuyten Duyvil
  // Harlem River, heading south
  [40.8730, -73.9110],
  [40.8620, -73.9150],
  [40.8460, -73.9280],
  [40.8280, -73.9340],
  [40.8130, -73.9340],
  [40.8070, -73.9320],
  [40.8000, -73.9280],
  // East River, heading south
  [40.7850, -73.9400],
  [40.7700, -73.9460],
  [40.7570, -73.9580],
  [40.7480, -73.9680],
  [40.7360, -73.9740],
  [40.7290, -73.9730],
  [40.7190, -73.9750],
  [40.7110, -73.9790], // Corlears Hook
  [40.7080, -73.9920],
  [40.7060, -73.9980],
  [40.7030, -74.0060],
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
  return isInsidePolygon(point, MANHATTAN_OUTLINE);
}
