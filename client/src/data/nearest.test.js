import { expect, it } from "vitest";
import { nearestPlaces } from "./nearest";

it("picks the nearest few of each category, whatever the order they come in", () => {
  const places = [
    { id: "a", category: "park", minutes: 9 },
    { id: "b", category: "park", minutes: 2 },
    { id: "c", category: "park", minutes: 5 },
    { id: "d", category: "park", minutes: 7 },
    { id: "e", category: "school", minutes: 12 },
  ];
  expect([...nearestPlaces(places)].sort()).toEqual(["park:b", "park:c", "park:d", "school:e"]);
});
