// The city grid (cards 12 and 15): every 100 m of land, scored ahead of time
// by server/scripts/build_grid.py, one file per borough. The site serves the
// files itself (client/scripts/fetch-grid.mjs copies them in at build time),
// so the score map works even while the API sleeps.
//
// A file lists its squares as 9 numbers each: column, row, the score in each
// of the six categories, and flags (bit k: nothing of category k within 15
// minutes; bit 6: mostly park). decodeGrid turns that into one array per
// square, [lat, lng, scores, flags, col, row]. Park squares are left out of
// the score map and the gaps, since nobody lives there. A file also lists
// the outlines of its parks (blank on the gap finder) and lakes (blank on both maps).

const FIELDS = 9;

export function decodeGrid(file) {
  const { meta } = file;
  const [lat0, lng0] = meta.origin;
  const [stepLat, stepLng] = meta.step;
  const n = meta.categories.length;
  const cells = [];
  for (let i = 0; i < file.cells.length; i += FIELDS) {
    const col = file.cells[i];
    const row = file.cells[i + 1];
    cells.push([
      lat0 + (row + 0.5) * stepLat,
      lng0 + (col + 0.5) * stepLng,
      file.cells.slice(i + 2, i + 2 + n),
      file.cells[i + 2 + n],
      col,
      row,
    ]);
  }
  return { meta, cells, gaps: file.gaps, parks: file.parks, water: file.water };
}

const GRID_BASE = `${import.meta.env.BASE_URL}grid/`;

// Which file holds each borough's grid. The names change with the contents,
// so browsers may keep the files; the index itself is checked every time.
export async function loadGridIndex(fetchFn = fetch) {
  const res = await fetchFn(`${GRID_BASE}index.json`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`The map data index couldn't be loaded (${res.status}).`);
  // Without the index, Vite's dev server answers with the page itself.
  return res.json().catch(() => {
    throw new Error("The map data isn't set up here. Run npm run dev again to copy it in.");
  });
}

export async function loadBoroughGrid(path, fetchFn = fetch) {
  const res = await fetchFn(`${GRID_BASE}${path}`);
  if (!res.ok) throw new Error(`The map data couldn't be loaded (${res.status}).`);
  return decodeGrid(await res.json());
}

// Every loaded borough's squares and outlines together, for drawing.
export function combineGrids(grids) {
  const loaded = Object.values(grids);
  if (!loaded.length) return null;
  const { categories } = loaded[0].meta;
  return {
    meta: loaded[0].meta,
    cells: loaded.flatMap((g) => g.cells),
    parks: loaded.flatMap((g) => g.parks),
    water: loaded.flatMap((g) => g.water),
    // For each category, every loaded borough's best spot for a new place.
    best: Object.fromEntries(
      categories.map((c) => [
        c,
        loaded.filter((g) => g.gaps[c].best).map((g) => ({ borough: g.meta.borough, spot: g.gaps[c].best })),
      ])
    ),
  };
}

function parkBit(categories) {
  return 1 << categories.length;
}

export function inPark(cell, categories) {
  return (cell[3] & parkBit(categories)) !== 0;
}

// The heat map's colors: viridis, a palette that stays in order for
// color-blind viewers and in grayscale. Scores between two stops blend.
// Canvas can't read CSS variables, so the colors live here.
const HEAT_STOPS = [
  [0, [68, 1, 84]], // #440154
  [25, [59, 82, 139]], // #3b528b
  [50, [33, 145, 140]], // #21918c
  [75, [94, 201, 98]], // #5ec962
  [100, [253, 231, 37]], // #fde725
];

// The legend's labels, matching the verdicts in categories.js at each end.
export const HEAT_LEGEND = {
  low: "Little nearby",
  high: "Everything nearby",
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

// Squares with nothing of one category within 15 minutes, outside the parks.
export function isGap(cell, categories, categoryId) {
  return !inPark(cell, categories) && (cell[3] & (1 << categories.indexOf(categoryId))) !== 0;
}
