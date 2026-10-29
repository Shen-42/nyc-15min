import { apiFetch } from "./api";
import { worthRetrying } from "./errors";

// Wait this long before trying the shaded area a second time.
export const AREA_RETRY_DELAY_MS = 1500;

// The shaded walking area for a search (card 14). It's the slowest request
// and the least important (the score and places come separately), so a
// failure is tried once more before giving up.
//   Resolves to the response body, or null when the server turned the spot
//   away (water, a park): the places request shows that message.
//   Rejects if both tries fail.
export async function fetchArea(query, { wait = AREA_RETRY_DELAY_MS } = {}) {
  let lastError = new Error("The shaded area couldn't be loaded.");
  for (let attempt = 0; attempt < 2; attempt++) {
    if (attempt > 0) await new Promise((resolve) => setTimeout(resolve, wait));
    try {
      const res = await apiFetch(`/api/area?${query}`);
      if (res.ok) return await res.json();
      if (!worthRetrying(res.status)) return null;
      lastError = new Error(`error ${res.status}`);
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError;
}
