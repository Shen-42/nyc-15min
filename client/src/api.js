// Where the API lives.
// In development this is empty: Vite forwards /api to localhost:8000 (see vite.config.js).
// On Render, VITE_API_URL is set to the API service's address at build time,
// for example https://nyc-15min-api.onrender.com
const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export function apiFetch(path) {
  return fetch(`${API_URL}${path}`);
}

// Render's free plan puts the API to sleep after 15 minutes without visits,
// and waking it takes about a minute. If a request is still waiting after
// this long, the app says so instead of looking frozen.
export const SLOW_REQUEST_MS = 3000;
