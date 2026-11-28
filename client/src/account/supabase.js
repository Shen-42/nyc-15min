// Sign-in (card 13). The browser only uses Supabase to sign people in; saved
// places and profiles go through our API, which checks the sign-in itself.
// The publishable key is meant to be public: on its own it can't read or
// write any table (row-level security, supabase/schema.sql).
// Without these settings (client/.env.local, or the site's Environment page
// on Render) the site works as before, with no sign-in.
// Only the project's address is wanted (https://<project>.supabase.co). The
// dashboard also shows it with /rest/v1 on the end; that would break sign-in,
// so anything after the host is dropped.
const url = import.meta.env.VITE_SUPABASE_URL?.match(/^https?:\/\/[^/]+/)?.[0];
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const authEnabled = Boolean(url && key);

// Supabase's code is a large part of the site's script, and most visitors
// never sign in, so it's downloaded only when needed: loadSupabase() fetches
// it and makes the client, once. supabaseReady resolves with the client
// whenever that happens, so code can wait for it without causing it.
let resolveReady;
export const supabaseReady = new Promise((resolve) => (resolveReady = resolve));
let loading = null;

export function loadSupabase() {
  loading ??= import("@supabase/supabase-js")
    .then(({ createClient }) => {
      const client = createClient(url, key);
      resolveReady(client);
      return client;
    })
    .catch((err) => {
      // The download failed: the next call tries again.
      loading = null;
      throw err;
    });
  return loading;
}

// Whether Supabase is needed as soon as the page opens: someone signed in on
// an earlier visit (Supabase keeps the session in localStorage under this
// name), or arrived from a confirmation or password-reset email (Supabase
// reads these from the address and signs them in).
export function neededAtStart() {
  if (!authEnabled) return false;
  const stored = `sb-${new URL(url).hostname.split(".")[0]}-auth-token`;
  let signedIn = false;
  try {
    signedIn = localStorage.getItem(stored) !== null;
  } catch {
    // Storage blocked: Supabase can't keep a session then either.
  }
  const params = new URLSearchParams(window.location.search + "&" + window.location.hash.slice(1));
  return signedIn || ["access_token", "code", "error", "error_description", "error_code"].some((p) => params.has(p));
}
