import { beforeEach, expect, it, vi } from "vitest";

// supabase.js reads its settings when it loads, so each test loads it afresh.
async function load() {
  vi.resetModules();
  vi.stubEnv("VITE_SUPABASE_URL", "https://abcdefgh.supabase.co/rest/v1");
  vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test");
  return import("./supabase");
}

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState(null, "", "/");
});

it("isn't needed at start for a visitor who never signed in", async () => {
  window.history.replaceState(null, "", "/?lat=40.7&lng=-73.9");
  expect((await load()).neededAtStart()).toBe(false);
});

it("is needed at start when a session from an earlier visit is stored", async () => {
  localStorage.setItem("sb-abcdefgh-auth-token", "{}");
  expect((await load()).neededAtStart()).toBe(true);
});

it("is needed at start when arriving from a sign-in email", async () => {
  window.history.replaceState(null, "", "/#access_token=x&type=recovery");
  expect((await load()).neededAtStart()).toBe(true);
  window.history.replaceState(null, "", "/?code=x");
  expect((await load()).neededAtStart()).toBe(true);
  window.history.replaceState(null, "", "/#error=access_denied&error_description=expired");
  expect((await load()).neededAtStart()).toBe(true);
});
