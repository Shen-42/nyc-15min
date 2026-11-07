// How many places of each category get a full marker on the map: the ones
// the panel lists as nearest. The rest are small dots, so a dense block reads
// as "these are the closest" rather than a pile of circles. Selecting a
// category in the panel brings all of its markers to full size (map.css).
const FULL_MARKERS_PER_CATEGORY = 3;

// The nearest few places in each category, as a set of "category:id" keys.
export function nearestPlaces(places, perCategory = FULL_MARKERS_PER_CATEGORY) {
  const counts = {};
  const nearest = new Set();
  for (const place of [...places].sort((a, b) => a.minutes - b.minutes)) {
    counts[place.category] = (counts[place.category] ?? 0) + 1;
    if (counts[place.category] <= perCategory) nearest.add(`${place.category}:${place.id}`);
  }
  return nearest;
}
