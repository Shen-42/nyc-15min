// The Manhattan grid (card 12): every 100 m of land, scored ahead of time by
// server/scripts/build_grid.py. Each cell is [lat, lng, [score per
// category], [minutes to the nearest place per category, or null], 1 if
// mostly inside a park]. Park cells are left out of the score map and the
// gaps, since nobody lives there. The grid also lists "blank" outlines (big
// parks and lakes) that the map leaves empty.

export function inPark(cell) {
  return cell[4] === 1;
}

// The heat map's colors: viridis, a palette that stays in order for
// color-blind viewers and in grayscale. Scores between two stops blend.
// Canvas can't read CSS variables, so the colors live here.
export const HEAT_STOPS = [
  [0, [68, 1, 84]], // #440154
  [25, [59, 82, 139]], // #3b528b
  [50, [33, 145, 140]], // #21918c
  [75, [94, 201, 98]], // #5ec962
  [100, [253, 231, 37]], // #fde725
];

// The legend's labels, matching the verdicts in categories.js at each end.
export const HEAT_LEGEND = {
  low: "Little within a 15-minute walk",
  high: "Errands all a short walk away",
  ticks: [0, 25, 50, 75, 100],
};

// [r, g, b] for a score from 0 to 100.
export function heatColor(score) {
  const s = Math.max(0, Math.min(100, score));
  for (let i = 1; i < HEAT_STOPS.length; i++) {
    const [s1, c1] = HEAT_STOPS[i];
    if (s <= s1) {
      const [s0, c0] = HEAT_STOPS[i - 1];
      const t = (s - s0) / (s1 - s0);
      return c0.map((v, k) => Math.round(v + t * (c1[k] - v)));
    }
  }
  return HEAT_STOPS[HEAT_STOPS.length - 1][1];
}

// The same colors as a CSS gradient, for the legend bar.
export const HEAT_GRADIENT = `linear-gradient(to right, ${HEAT_STOPS.map(
  ([s, [r, g, b]]) => `rgb(${r} ${g} ${b}) ${s}%`
).join(", ")})`;

// "#b84a00" -> [184, 74, 0]
export function hexToRgb(hex) {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

// A cell's overall score with the visitor's weights, the same formula as
// the server: the weighted average of the category scores.
export function cellScore(cell, categories, weights) {
  let sum = 0;
  let total = 0;
  categories.forEach((id, k) => {
    sum += weights[id] * cell[2][k];
    total += weights[id];
  });
  return total ? Math.round(sum / total) : 0;
}

// Cells with nothing of one category within 15 minutes, outside the big parks.
export function isGap(cell, categories, categoryId) {
  return !inPark(cell) && cell[3][categories.indexOf(categoryId)] === null;
}
