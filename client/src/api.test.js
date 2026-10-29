import { afterEach, expect, it, vi } from "vitest";
import { apiFetch } from "./api";

afterEach(() => vi.unstubAllGlobals());

it("gives up on a request that takes too long", async () => {
  // A server that never answers: the request only ends when it's aborted.
  vi.stubGlobal(
    "fetch",
    vi.fn((url, init) => new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(init.signal.reason))))
  );
  await expect(apiFetch("/api/places", { timeoutMs: 20 })).rejects.toMatchObject({ name: "TimeoutError" });
});

it("passes other options through", async () => {
  const fetch = vi.fn(() => Promise.resolve(new Response("{}")));
  vi.stubGlobal("fetch", fetch);
  await apiFetch("/api/health", { cache: "no-store" });
  expect(fetch.mock.calls[0][1].cache).toBe("no-store");
  expect(fetch.mock.calls[0][1].signal).toBeDefined();
});
