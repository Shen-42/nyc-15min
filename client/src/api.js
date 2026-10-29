// Where the API lives.
// In development this is empty: Vite forwards /api to localhost:8000 (see vite.config.js).
// On Render, VITE_API_URL is set to the API service's address at build time,
// for example https://nyc-15min-api.onrender.com
const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

// Give up on a request after this long (card 14). Longer than the API
// takes to wake up on Render's free plan (about a minute), so a slow start
// still gets through, but a hung request doesn't spin forever.
export const REQUEST_TIMEOUT_MS = 70_000;

// fetch() with a timeout. When time runs out the promise rejects with a
// TimeoutError, which errors.js turns into a readable message.
export function apiFetch(path, options = {}) {
  const { timeoutMs = REQUEST_TIMEOUT_MS, ...init } = options;
  const signal = init.signal ?? AbortSignal.timeout(timeoutMs);
  return fetch(`${API_URL}${path}`, { ...init, signal });
}

// Render's free plan puts the API to sleep after 15 minutes without visits,
// and waking it takes about a minute. If a request is still waiting after
// this long, the app says so instead of looking frozen.
export const SLOW_REQUEST_MS = 3000;
