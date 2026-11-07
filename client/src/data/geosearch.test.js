import { afterEach, expect, it, vi } from "vitest";
import { MAX_SUGGESTIONS, findAddresses, tidyLabel } from "./geosearch";

afterEach(() => vi.unstubAllGlobals());

function answer(features, status = 200) {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ features }), { status }))));
}

const point = (label, lng, lat) => ({ geometry: { type: "Point", coordinates: [lng, lat] }, properties: { label } });

it("turns GeoSearch's answer into labels and points", async () => {
  answer([point("120 BROADWAY, Manhattan, New York, NY, USA", -74.0106, 40.7083)]);
  expect(await findAddresses("120 broad")).toEqual([
    { label: "120 Broadway, Manhattan, New York, NY", lat: 40.7083, lng: -74.0106 },
  ]);
  expect(fetch.mock.calls[0][0]).toContain("/autocomplete?text=120%20broad");
});

it("keeps only a few suggestions", async () => {
  answer(Array.from({ length: 10 }, (_, i) => point(`${i} Main St`, -73.9, 40.7)));
  expect(await findAddresses("main")).toHaveLength(MAX_SUGGESTIONS);
});

it("says so when the search service fails", async () => {
  answer([], 503);
  await expect(findAddresses("main")).rejects.toThrow("503");
});

it("writes street names in title case, not capitals", () => {
  expect(tidyLabel("350 WEST 42 STREET, Manhattan, New York, NY, USA")).toBe("350 West 42nd Street, Manhattan, New York, NY");
  expect(tidyLabel("15-05 149 PLACE, Queens, NY, USA")).toBe("15-05 149th Place, Queens, NY");
  expect(tidyLabel("2 EAST 111 STREET, Manhattan, NY")).toBe("2 East 111th Street, Manhattan, NY");
  expect(tidyLabel("100 BEACH 23 STREET, Queens, NY")).toBe("100 Beach 23rd Street, Queens, NY");
  expect(tidyLabel("100 1ST AVENUE, Manhattan, NY")).toBe("100 1st Avenue, Manhattan, NY");
  expect(tidyLabel("3 AVENUE U, Brooklyn, NY")).toBe("3 Avenue U, Brooklyn, NY");
  expect(tidyLabel("1211 AVENUE OF THE AMERICAS, Manhattan, NY")).toBe("1211 Avenue of the Americas, Manhattan, NY");
  expect(tidyLabel("10 MCGUINNESS BOULEVARD, Brooklyn, NY")).toBe("10 McGuinness Boulevard, Brooklyn, NY");
  expect(tidyLabel("5 O'BRIEN PLACE, Bronx, NY")).toBe("5 O'Brien Place, Bronx, NY");
});
