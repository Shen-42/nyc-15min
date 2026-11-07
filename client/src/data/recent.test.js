import { beforeEach, expect, it } from "vitest";
import { MAX_RECENT, addRecent, describeSpot, loadRecent } from "./recent";

beforeEach(() => localStorage.clear());

it("keeps the newest few spots, newest first, without repeats", () => {
  let list = [];
  for (let i = 0; i < MAX_RECENT + 2; i++) list = addRecent(list, { label: `Spot ${i}`, lat: 40.7 + i / 100, lng: -73.9 });
  list = addRecent(list, { label: "Spot 6 again", lat: 40.76, lng: -73.9 });
  expect(list.map((s) => s.label)).toEqual(["Spot 6 again", "Spot 5", "Spot 4", "Spot 3", "Spot 2"]);
  expect(loadRecent()).toEqual(list);
});

it("names a map spot by its nearest subway station", () => {
  const places = [
    { category: "subway", name: "86th Street", minutes: 6 },
    { category: "subway", name: "72nd Street", minutes: 3 },
    { category: "park", name: "Central Park", minutes: 1 },
  ];
  expect(describeSpot(places, "Manhattan")).toBe("Near 72nd Street, Manhattan");
  expect(describeSpot([], "Staten Island")).toBe("A spot in Staten Island");
});
