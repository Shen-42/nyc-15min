import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api";
import { supabase } from "./supabase";

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

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((event, next) => {
      setSession(next);
      if (event === "PASSWORD_RECOVERY") setRecovering(true);
    });
    return () => data.subscription.unsubscribe();
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
    enabled: Boolean(supabase),
    session,
    user,
    authFetch,
    recovering,
    endRecovery: () => setRecovering(false),
    notice,
    setNotice,
    signOut: () => supabase.auth.signOut(),
  };
}
