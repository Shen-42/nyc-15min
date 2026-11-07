// The last few spots looked at, kept in this browser (heuristic 6: show
// them, rather than make people remember and retype them). Shown in the
// address box's list when it's empty.
const KEY = "nyc15min.recentSpots";
export const MAX_RECENT = 5;

export function loadRecent() {
  try {
    const list = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(list) ? list.filter((s) => s && typeof s.label === "string").slice(0, MAX_RECENT) : [];
  } catch {
    return []; // private browsing, or storage turned off
  }
}

// Puts a spot first, removes an older copy of it (same place to about 10 m),
// keeps the newest MAX_RECENT, and returns the new list.
export function addRecent(list, spot) {
  const same = (a) => a.lat.toFixed(4) === spot.lat.toFixed(4) && a.lng.toFixed(4) === spot.lng.toFixed(4);
  const next = [spot, ...list.filter((s) => !same(s))].slice(0, MAX_RECENT);
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Not saved, but this visit's list still works.
  }
  return next;
}

// A name for a spot picked on the map, from what the search found there:
// its nearest subway station and borough, e.g. "Near 72nd Street, Manhattan".
export function describeSpot(places, borough) {
  const station = places
    .filter((p) => p.category === "subway" && p.name)
    .sort((a, b) => a.minutes - b.minutes)[0];
  if (station) return borough ? `Near ${station.name}, ${borough}` : `Near ${station.name}`;
  return borough ? `A spot in ${borough}` : "A spot on the map";
}
