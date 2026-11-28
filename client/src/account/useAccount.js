import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api";
import { authEnabled, loadSupabase, neededAtStart, supabaseReady } from "./supabase";

// Who is signed in, and a fetch that sends their token (card 13).
//
// session: Supabase's session, or null. user: { id, email, role } from our
// API's /api/me, so the role comes from the server, not the browser.
// recovering: true after following a password-reset link, until a new
// password is set. notice: a message for the panel, e.g. a session that
// expired.
export function useAccount() {
  const [session, setSession] = useState(null);
  const [user, setUser] = useState(null);
  const [recovering, setRecovering] = useState(false);
  const [notice, setNotice] = useState(null);

  // Supabase loads now only if it's needed at once (supabase.js); otherwise
  // when the sign-in dialog first uses it. Either way, follow the session
  // from then on.
  useEffect(() => {
    if (!authEnabled) return;
    // If it can't be downloaded, the visitor shows as signed out, and
    // signing in tries again.
    if (neededAtStart()) loadSupabase().catch(() => {});
    let subscription = null;
    let current = true;
    supabaseReady.then((supabase) => {
      if (!current) return;
      supabase.auth.getSession().then(({ data }) => setSession(data.session));
      ({ data: { subscription } } = supabase.auth.onAuthStateChange((event, next) => {
        setSession(next);
        if (event === "PASSWORD_RECOVERY") setRecovering(true);
      }));
    });
    return () => {
      current = false;
      subscription?.unsubscribe();
    };
  }, []);

  // Sends the request with the current token. If the server says the token
  // expired (the tab was left open a long time, say), refresh it once and
  // try again; if that fails too, sign out and say why.
  const authFetch = useCallback(async (path, options = {}) => {
    const send = (token) =>
      apiFetch(path, {
        ...options,
        headers: {
          ...(options.body ? { "Content-Type": "application/json" } : {}),
          ...options.headers,
          Authorization: `Bearer ${token}`,
        },
      });
    const supabase = await loadSupabase();
    const { data } = await supabase.auth.getSession();
    if (!data.session) throw new Error("Sign in to continue.");
    let res = await send(data.session.access_token);
    if (res.status === 401) {
      const refreshed = await supabase.auth.refreshSession();
      if (refreshed.data.session) res = await send(refreshed.data.session.access_token);
      if (res.status === 401) {
        await supabase.auth.signOut();
        setNotice({ kind: "warn", text: "Your session expired. Sign in again to continue." });
      }
    }
    return res;
  }, []);

  const userId = session?.user?.id;
  useEffect(() => {
    if (!userId) {
      setUser(null);
      return;
    }
    let current = true;
    authFetch("/api/me")
      .then((res) => (res.ok ? res.json() : null))
      .then((me) => current && setUser(me))
      .catch(() => current && setUser(null));
    return () => {
      current = false;
    };
  }, [userId, authFetch]);

  return {
    enabled: authEnabled,
    session,
    user,
    authFetch,
    recovering,
    endRecovery: () => setRecovering(false),
    notice,
    setNotice,
    signOut: () => loadSupabase().then((supabase) => supabase.auth.signOut()),
  };
}
