// Needs profiles (card 9): how much each kind of place matters to someone.
// The weights use the same 0-3 scale as CATEGORY_SETTINGS in
// server/scoring.py, where 0 leaves a category out of the score.

// Most important first, so the dropdown reads top to bottom.
export const IMPORTANCE = [
  { value: 3, label: "Essential" },
  { value: 2, label: "Important" },
  { value: 1, label: "Nice to have" },
  { value: 0, label: "Not needed" },
];

// The server's own defaults: groceries count most, then the subway.
export const DEFAULT_WEIGHTS = { grocery: 3, subway: 2, pharmacy: 1, clinic: 1, park: 1, school: 1 };

// Starting points people can pick and then adjust. These are judgment calls,
// not survey results.
export const PRESETS = [
  { id: "default", label: "Default", weights: DEFAULT_WEIGHTS },
  {
    id: "student",
    label: "Student",
    // Gets around by subway and shops on a budget. Schools here are K-12, so
    // they don't matter.
    weights: { grocery: 3, subway: 3, pharmacy: 1, clinic: 1, park: 2, school: 0 },
  },
  {
    id: "parent",
    label: "Parent",
    // School and playgrounds every day, the pediatrician and pharmacy often.
    weights: { grocery: 3, subway: 2, pharmacy: 2, clinic: 2, park: 3, school: 3 },
  },
  {
    id: "retiree",
    label: "Retiree",
    // Doctors and the pharmacy come first. No school runs.
    weights: { grocery: 3, subway: 2, pharmacy: 3, clinic: 3, park: 2, school: 0 },
  },
];

// The preset these weights match exactly, or null for a custom mix.
export function matchingPreset(weights) {
  return (
    PRESETS.find((preset) => Object.entries(preset.weights).every(([id, w]) => weights[id] === w)) ?? null
  );
}

// The form the server reads: "grocery:3,subway:2,...".
export function weightsToQuery(weights) {
  return Object.entries(weights)
    .map(([id, w]) => `${id}:${w}`)
    .join(",");
}

export function hasAnyWeight(weights) {
  return Object.values(weights).some((w) => w > 0);
}

// The browser remembers the last profile. Storage can be blocked (private
// windows, strict settings), so every read and write is allowed to fail.
const STORAGE_KEY = "nyc15min.weights";

export function loadWeights() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (!saved || typeof saved !== "object") return DEFAULT_WEIGHTS;
    const weights = {};
    for (const [id, fallback] of Object.entries(DEFAULT_WEIGHTS)) {
      const w = saved[id];
      weights[id] = Number.isInteger(w) && w >= 0 && w <= 3 ? w : fallback;
    }
    return hasAnyWeight(weights) ? weights : DEFAULT_WEIGHTS;
  } catch {
    return DEFAULT_WEIGHTS;
  }
}

export function saveWeights(weights) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(weights));
  } catch {
    // Nothing to do: the profile just won't be remembered next visit.
  }
}
