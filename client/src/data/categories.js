// The six kinds of places, in the order the panel lists them (heaviest
// weight first, matching CATEGORY_SETTINGS in server/scoring.py).
// Each has a short glyph so the map and panel never rely on color alone
// (WCAG 1.4.1). Colors live in styles/tokens.css as --cat-<id>.
// "one" is the singular, for sentences like "no grocery store within 15 minutes".
export const CATEGORIES = [
  { id: "grocery", label: "Groceries", one: "grocery store", glyph: "G" },
  { id: "subway", label: "Subway stations", one: "subway station", glyph: "T" },
  { id: "pharmacy", label: "Pharmacies", one: "pharmacy", glyph: "Rx" },
  { id: "clinic", label: "Doctors and clinics", one: "doctor or clinic", glyph: "+" },
  { id: "park", label: "Parks", one: "park", glyph: "P" },
  { id: "school", label: "Schools", one: "school", glyph: "S" },
];

export const CATEGORY_BY_ID = Object.fromEntries(CATEGORIES.map((c) => [c.id, c]));

// One sentence for the overall score, so the number means something.
export function verdict(score) {
  if (score >= 90) return "Daily errands are all a short walk away.";
  if (score >= 75) return "Most daily errands can be done on foot.";
  if (score >= 50) return "Some daily errands can be done on foot.";
  if (score >= 25) return "A few things are within walking distance.";
  return "Little is within a 15-minute walk.";
}
