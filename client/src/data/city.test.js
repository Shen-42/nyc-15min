import { describe, expect, it } from "vitest";
import { BOROUGHS, boroughAt, boxesOverlap, isInCity } from "./city";

describe("the five boroughs (card 15)", () => {
  it("finds the borough a spot is in", () => {
    expect(boroughAt([40.758, -73.9855]).name).toBe("Manhattan"); // Times Square
    expect(boroughAt([40.6782, -73.9442]).name).toBe("Brooklyn"); // Crown Heights
    expect(boroughAt([40.759, -73.8303]).name).toBe("Queens"); // Flushing
    expect(boroughAt([40.8448, -73.8648]).name).toBe("Bronx"); // Parkchester
    expect(boroughAt([40.5795, -74.1502]).name).toBe("Staten Island"); // New Springville
  });

  it("leaves out the rivers and New Jersey", () => {
    expect(isInCity([40.706, -73.996])).toBe(false); // East River under the Brooklyn Bridge
    expect(isInCity([40.7178, -74.0431])).toBe(false); // Jersey City
  });

  it("knows which boroughs a view overlaps", () => {
    const midtown = [
      [40.75, -74.0],
      [40.77, -73.97],
    ];
    const overlapping = BOROUGHS.filter((b) => boxesOverlap(b.allBounds, midtown)).map((b) => b.name);
    expect(overlapping).toContain("Manhattan");
    expect(overlapping).not.toContain("Staten Island");
  });
});
