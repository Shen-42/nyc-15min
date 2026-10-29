// Readable messages for everything that can go wrong with a request (card 14).

// The message for an error response. The API answers with { detail: "..." };
// FastAPI's own input checks used to answer with a list, so that's handled too.
export async function errorText(res, fallback) {
  const body = await res.json().catch(() => ({}));
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  if (fallback) return fallback;
  if (res.status >= 500) return `Something went wrong on our side (error ${res.status}). Try again in a minute.`;
  return `The request didn't work (error ${res.status}).`;
}

// The message for a request that never got an answer.
export function failureText(err) {
  if (err?.name === "TimeoutError") return "The server took too long to answer. It may still be waking up.";
  return "Can't reach the server. Check your connection, then try again.";
}

// Whether trying the same request again could help. A 422 (water, a park,
// too far from a street) or 429 (too many searches) won't change right away.
export function worthRetrying(status) {
  return status >= 500 || status === 408;
}
