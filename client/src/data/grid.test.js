import { describe, expect, it } from "vitest";
import { cellScore, combineGrids, decodeGrid, inPark, isGap } from "./grid";

const CATEGORIES = ["grocery", "pharmacy", "clinic", "park", "school", "subway"];
const PARK = 1 << 6;

// A borough file as build_grid.py writes it: 9 numbers per square.
function file(borough, cells, best = null) {
  return {
    meta: { borough, categories: CATEGORIES, origin: [40.5, -74.2], step: [0.001, 0.002] },
    cells: cells.flat(),
    gaps: Object.fromEntries(CATEGORIES.map((c) => [c, { cells: 0, best: c === "grocery" ? best : null }])),
    parks: [],
    water: [],
  };
}

describe("the city grid (card 15)", () => {
  const grid = decodeGrid(
    file("Queens", [
      [3, 2, 90, 80, 70, 60, 50, 40, 0], // everything in reach
      [4, 2, 0, 80, 70, 60, 50, 0, 1 | 32], // no grocery (bit 0) and no subway (bit 5)
      [5, 2, 100, 100, 100, 100, 100, 100, PARK], // a park
    ])
  );

  it("puts each square at its column and row", () => {
    const [lat, lng, scores, flags, col, row] = grid.cells[0];
    expect(lat).toBeCloseTo(40.5 + 2.5 * 0.001);
    expect(lng).toBeCloseTo(-74.2 + 3.5 * 0.002);
    expect(scores).toEqual([90, 80, 70, 60, 50, 40]);
    expect([flags, col, row]).toEqual([0, 3, 2]);
  });

  it("reads gaps and parks from the flags", () => {
    expect(isGap(grid.cells[1], CATEGORIES, "grocery")).toBe(true);
    expect(isGap(grid.cells[1], CATEGORIES, "subway")).toBe(true);
    expect(isGap(grid.cells[1], CATEGORIES, "pharmacy")).toBe(false);
    expect(inPark(grid.cells[2], CATEGORIES)).toBe(true);
    expect(isGap(grid.cells[2], CATEGORIES, "grocery")).toBe(false); // a park is never a gap
  });

  it("scores a square with the visitor's weights", () => {
    const groceriesOnly = Object.fromEntries(CATEGORIES.map((c) => [c, c === "grocery" ? 3 : 0]));
    expect(cellScore(grid.cells[0], CATEGORIES, groceriesOnly)).toBe(90);
  });

  it("combines the loaded boroughs and keeps each one's best spot", () => {
    const spot = { lat: 40.6, lng: -73.9, fixes: 12, near: "Main St & 1st Ave" };
    const combined = combineGrids({
      queens: grid,
      bronx: decodeGrid(file("Bronx", [[1, 1, 1, 1, 1, 1, 1, 1, 0]], spot)),
    });
    expect(combined.cells).toHaveLength(4);
    expect(combined.best.grocery).toEqual([{ borough: "Bronx", spot }]);
    expect(combined.best.subway).toEqual([]);
    expect(combineGrids({})).toBeNull();
  });
});
