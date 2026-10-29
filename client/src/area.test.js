import { beforeEach, expect, it, vi } from "vitest";

vi.mock("./api", () => ({ apiFetch: vi.fn() }));
const { apiFetch } = await import("./api");
const { fetchArea } = await import("./area");

const ok = () => new Response(JSON.stringify({ area: { type: "Polygon", coordinates: [] } }), { status: 200 });

beforeEach(() => apiFetch.mockReset());

it("tries the area again once after a failure", async () => {
  apiFetch.mockRejectedValueOnce(new TypeError("Failed to fetch")).mockResolvedValueOnce(ok());
  expect(await fetchArea("lat=1&lng=2", { wait: 0 })).toHaveProperty("area");
  expect(apiFetch).toHaveBeenCalledTimes(2);
});

it("gives up after the second failure", async () => {
  apiFetch.mockResolvedValue(new Response("", { status: 503 }));
  await expect(fetchArea("lat=1&lng=2", { wait: 0 })).rejects.toThrow();
  expect(apiFetch).toHaveBeenCalledTimes(2);
});

it("doesn't retry a spot the server turned away", async () => {
  apiFetch.mockResolvedValue(new Response(JSON.stringify({ detail: "That spot is in the Reservoir." }), { status: 422 }));
  expect(await fetchArea("lat=1&lng=2", { wait: 0 })).toBeNull();
  expect(apiFetch).toHaveBeenCalledTimes(1);
});
