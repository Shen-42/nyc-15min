import { useEffect, useRef, useState } from "react";
import { CATEGORIES } from "../data/categories";
import { errorText } from "./errors";

// Wait this long after the last change to "Your needs" before saving it.
const PROFILE_SAVE_DELAY_MS = 800;

// The same needs in a stable form, to tell whether they changed.
const needsKey = (weights, mode) => `${CATEGORIES.map((c) => weights[c.id]).join(",")}:${mode}`;

// The signed-in person's saved places and needs profile (card 13).
//
// On sign-in, both are loaded. A saved profile replaces this browser's
// settings; with none saved yet, this browser's settings become the profile.
// After that, every change is saved, tagged with the version it started
// from. If another tab or device saved in between, the server refuses the
// save and sends the latest profile, which is shown instead with a notice.
export function useAccountData({ account, weights, mode, setWeights, setMode }) {
  const [places, setPlaces] = useState([]);
  const [ready, setReady] = useState(false);
  const version = useRef(0);
  const synced = useRef(null);
  const userId = account.session?.user?.id;
  const { authFetch, setNotice } = account;

  function apply(profile) {
    version.current = profile.version;
    synced.current = needsKey(profile.weights, profile.mode);
    setWeights(profile.weights);
    setMode(profile.mode);
  }

  useEffect(() => {
    setReady(false);
    setPlaces([]);
    version.current = 0;
    synced.current = null;
    if (!userId) return;
    let current = true;
    (async () => {
      try {
        const [placesRes, profileRes] = await Promise.all([authFetch("/api/saved-places"), authFetch("/api/profile")]);
        if (!current) return;
        if (placesRes.ok) setPlaces((await placesRes.json()).places);
        if (profileRes.ok) {
          const { profile } = await profileRes.json();
          if (!current) return;
          if (profile) apply(profile);
          setReady(true);
        }
      } catch {
        // Offline or server asleep: keep working with this browser's settings.
      }
    })();
    return () => {
      current = false;
    };
  }, [userId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!ready || needsKey(weights, mode) === synced.current) return;
    const timer = setTimeout(async () => {
      try {
        const res = await authFetch("/api/profile", {
          method: "PUT",
          body: JSON.stringify({ weights, mode, version: version.current }),
        });
        if (res.ok) {
          const { profile } = await res.json();
          version.current = profile.version;
          synced.current = needsKey(profile.weights, profile.mode);
        } else if (res.status === 409) {
          const { profile } = await res.json();
          if (profile) apply(profile);
          setNotice({ kind: "warn", text: "Your needs were changed in another tab or device. Showing the latest." });
        }
      } catch {
        // Not saved this time; the next change tries again.
      }
    }, PROFILE_SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [ready, weights, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  async function removePlace(place) {
    setPlaces((list) => list.filter((p) => p.id !== place.id));
    try {
      const res = await authFetch(`/api/saved-places/${place.id}`, { method: "DELETE" });
      if (res.ok || res.status === 404) return;
      setNotice({ kind: "error", text: await errorText(res, `Couldn't remove ${place.name}. Try again.`) });
    } catch {
      setNotice({ kind: "error", text: `Couldn't remove ${place.name}. Try again.` });
    }
    setPlaces((list) => [...list, place].sort((a, b) => a.created_at.localeCompare(b.created_at)));
  }

  return {
    places,
    addPlace: (place) => setPlaces((list) => [...list, place]),
    removePlace,
  };
}
