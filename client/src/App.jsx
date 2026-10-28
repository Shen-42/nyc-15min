import { useEffect, useRef, useState } from "react";
import { SLOW_REQUEST_MS, apiFetch } from "./api";
import AccountDialog from "./account/AccountDialog";
import AuthDialog from "./account/AuthDialog";
import { useAccount } from "./account/useAccount";
import { useAccountData } from "./account/useAccountData";
import ManhattanMap from "./components/ManhattanMap";
import ResultsPanel from "./components/ResultsPanel";
import { isInManhattan } from "./data/manhattan";
import { loadMode, loadWeights, saveMode, saveWeights, weightsToQuery } from "./data/profiles";
import { atQuery, formatHour, nycNow } from "./data/time";

const MINUTES = 15;
// Wait this long after the last change to the needs form before re-scoring,
// so clicking through options sends one request, not five.
const RESCORE_DELAY_MS = 400;

export default function App() {
  const [serverDown, setServerDown] = useState(false);
  const [selectedPoint, setSelectedPoint] = useState(null);
  // status: "idle" | "loading" | "done"
  const [status, setStatus] = useState("idle");
  // The last successful search. Kept on screen while a new one loads.
  const [result, setResult] = useState(null);
  // { kind: "warn" | "error", text } or null
  const [message, setMessage] = useState(null);
  // The category whose places are highlighted on the map, or null.
  const [focus, setFocus] = useState(null);
  // On phones, where the bottom sheet sits: "hidden" (just its handle, so
  // the whole map shows), "peek" (title and score), or "open" (everything).
  const [sheet, setSheet] = useState("peek");
  // True while a request has taken long enough that the server is probably waking up.
  const [waking, setWaking] = useState(false);
  // How much each kind of place matters (card 9). Remembered by the browser.
  const [weights, setWeights] = useState(loadWeights);
  // The hour to check opening hours at (card 10), New York time, or null
  // for any time. Not remembered: "9 pm" means today's 9 pm.
  const [hour, setHour] = useState(null);
  // "walk" or "wheelchair" (card 11). Remembered by the browser.
  const [mode, setMode] = useState(loadMode);
  // What the map shows (card 12): "walk" (your walk), "heat" (score map), or "gaps".
  const [view, setView] = useState("walk");
  const [gapCategory, setGapCategory] = useState("grocery");
  // The Manhattan grid, loaded the first time the score map or gap finder opens.
  const [grid, setGrid] = useState(null);
  const [gridError, setGridError] = useState(null);
  // Accounts (card 13): who is signed in, their saved places, and which
  // dialog is open. authReason says why sign-in was asked for, or is null.
  const account = useAccount();
  const saved = useAccountData({ account, weights, mode, setWeights, setMode });
  const [authOpen, setAuthOpen] = useState(false);
  const [authReason, setAuthReason] = useState(null);
  const [accountOpen, setAccountOpen] = useState(false);
  // Where the map should move to, e.g. when a saved place is picked.
  const [flyTo, setFlyTo] = useState(null);
  // Counts requests so a slow old response can't replace a newer one.
  const latestRequest = useRef(0);
  // The same for re-scores after the needs form changes.
  const latestRescore = useRef(0);
  // Read inside async code, where the state values could be stale.
  const weightsRef = useRef(weights);
  const hourRef = useRef(hour);
  const modeRef = useRef(mode);
  const pointRef = useRef(null);

  // Wake the server as soon as the page opens, so it's likely ready by the
  // time someone picks a spot.
  useEffect(() => {
    const slow = setTimeout(() => setWaking(true), SLOW_REQUEST_MS);
    apiFetch("/api/health")
      .then((res) => setServerDown(!res.ok))
      .catch(() => setServerDown(true))
      .finally(() => {
        clearTimeout(slow);
        setWaking(false);
      });
  }, []);

  // When the needs form changes: remember it, and re-score the current spot.
  // Only the score and places are asked for again; the shaded area doesn't
  // depend on weights, so it stays as it is.
  // The same when the hour changes: opening hours don't change the area either.
  useEffect(() => {
    weightsRef.current = weights;
    hourRef.current = hour;
    saveWeights(weights);
    if (!pointRef.current) return;
    const timer = setTimeout(rescore, RESCORE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [weights, hour]);

  // Load the grid once, when it's first needed. It's about 100 KB compressed.
  useEffect(() => {
    if (view === "walk" || grid) return;
    setGridError(null);
    // "no-store": always ask the server, so a rebuilt grid is never hidden
    // behind an old copy in the browser's cache.
    apiFetch("/api/grid", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then(setGrid)
      .catch(() => setGridError("Couldn't load map data. Try again in a minute."));
  }, [view, grid]);

  // A new way of getting around changes the shaded area too, so search again in full.
  useEffect(() => {
    modeRef.current = mode;
    saveMode(mode);
    if (pointRef.current) findWalkingArea(pointRef.current);
  }, [mode]);

  // lat, lng, minutes, and the mode: what both requests share.
  function baseQuery(point) {
    const how = modeRef.current === "wheelchair" ? "&mode=wheelchair" : "";
    return `lat=${point[0]}&lng=${point[1]}&minutes=${MINUTES}${how}`;
  }

  function placesQuery(point) {
    const at = hourRef.current === null ? "" : `&at=${atQuery(hourRef.current)}`;
    return `${baseQuery(point)}&weights=${weightsToQuery(weightsRef.current)}${at}`;
  }

  async function rescore() {
    const point = pointRef.current;
    const searchId = latestRequest.current;
    const rescoreId = ++latestRescore.current;
    // A new click, or a newer re-score, makes this one out of date.
    const current = () => searchId === latestRequest.current && rescoreId === latestRescore.current;
    setStatus("loading");
    try {
      const res = await apiFetch(`/api/places?${placesQuery(point)}`);
      if (!current()) return;
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const text = typeof body.detail === "string" ? body.detail : `Couldn't update the score (error ${res.status}).`;
        setMessage({ kind: "warn", text });
        return;
      }
      const data = await res.json();
      if (!current()) return;
      setMessage(null);
      setResult((r) =>
        r?.id === searchId ? { ...r, places: data.amenities, score: data.score, barriers: data.barriers ?? [] } : r
      );
    } catch {
      if (current()) setServerDown(true);
    } finally {
      if (current()) setStatus("done");
    }
  }

  async function findWalkingArea(point) {
    const requestId = ++latestRequest.current;
    latestRescore.current++; // a pending re-score is for the old spot
    pointRef.current = point;
    const query = baseQuery(point);
    setStatus("loading");
    setMessage(null);
    const slow = setTimeout(() => {
      if (requestId === latestRequest.current) setWaking(true);
    }, SLOW_REQUEST_MS);

    // Two requests at once: the places and score come back quickly, and the
    // shaded area (slow to build on the free server) is drawn when it lands.
    const areaRequest = apiFetch(`/api/area?${query}`)
      .then((res) => (res.ok ? res.json() : null))
      .catch(() => null);

    try {
      const res = await apiFetch(`/api/places?${placesQuery(point)}`);
      if (requestId !== latestRequest.current) return;
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        // 422: the server turned the click away (water, no path nearby) and says why.
        // 429: too many searches in a minute.
        // 501: the search function isn't written yet.
        const explained = [422, 429, 501].includes(res.status);
        const text = explained
          ? body.detail
          : `The search failed (${body.detail ?? `error ${res.status}`}). Try another spot.`;
        setResult(null);
        setMessage({ kind: res.status === 422 || res.status === 429 ? "warn" : "error", text });
        setStatus("done");
        return;
      }
      const data = await res.json();
      if (requestId !== latestRequest.current) return;
      // Show the score and places now. The old area is cleared so it never
      // sits under the new dot.
      setResult({
        id: requestId,
        area: null,
        places: data.amenities,
        score: data.score,
        mode: data.mode ?? "walk",
        barriers: data.barriers ?? [],
      });
      setServerDown(false);
      setStatus("done");
    } catch {
      if (requestId !== latestRequest.current) return;
      // fetch() throws when the server can't be reached at all.
      setServerDown(true);
      setStatus("done");
      return;
    } finally {
      clearTimeout(slow);
      if (requestId === latestRequest.current) setWaking(false);
    }

    try {
      const areaData = await areaRequest;
      if (requestId !== latestRequest.current || !areaData) return;
      setResult((current) =>
        current?.id === requestId
          ? { ...current, area: { type: "Feature", properties: {}, geometry: areaData.area } }
          : current
      );
    } catch {
      // The panel already has its results; a missing shading isn't worth an error.
    }
  }

  function openSignIn(reason = null) {
    account.setNotice(null);
    setAuthReason(reason);
    setAuthOpen(true);
  }

  function goToPlace(place) {
    const point = [place.lat, place.lng];
    setFlyTo({ point, key: Date.now() });
    handleMapClick(point);
  }

  function handleMapClick(point) {
    setFocus(null);
    setView("walk"); // a click asks about one spot, so go back to your walk
    setSheet((s) => (s === "hidden" ? "peek" : s)); // and its score should show
    if (isInManhattan(point)) {
      setSelectedPoint(point);
      findWalkingArea(point);
    } else {
      latestRequest.current++; // ignore any search still in flight
      pointRef.current = null;
      setSelectedPoint(null);
      setResult(null);
      setStatus("idle");
      setMessage({ kind: "warn", text: "Only Manhattan is covered for now. Choose a spot on the island." });
    }
  }

  return (
    <div className="app">
      <ResultsPanel
        status={status}
        result={result}
        message={message}
        serverDown={serverDown}
        waking={waking}
        focus={focus}
        onFocus={setFocus}
        sheet={sheet}
        onSheetChange={setSheet}
        weights={weights}
        onWeightsChange={setWeights}
        hour={hour}
        onHourChange={setHour}
        timeLabel={hour === null ? null : `${formatHour(hour)} on ${nycNow().weekday}`}
        mode={mode}
        onModeChange={setMode}
        view={view}
        onViewChange={setView}
        grid={grid}
        gridError={gridError}
        gapCategory={gapCategory}
        onGapCategory={setGapCategory}
        selectedPoint={selectedPoint}
        account={account}
        savedPlaces={saved.places}
        onSignIn={openSignIn}
        onOpenAccount={() => setAccountOpen(true)}
        onPlaceSaved={saved.addPlace}
        onGoToPlace={goToPlace}
        onRemovePlace={saved.removePlace}
      />
      {account.enabled && (
        <>
          <AuthDialog
            open={authOpen || account.recovering}
            onClose={() => {
              setAuthOpen(false);
              account.endRecovery();
            }}
            reason={authReason}
            recovering={account.recovering}
            onRecovered={() => account.setNotice({ kind: "ok", text: "Password updated. You're signed in." })}
          />
          <AccountDialog
            open={accountOpen}
            onClose={() => setAccountOpen(false)}
            account={account}
            savedCount={saved.places.length}
            onDeleted={() => account.setNotice({ kind: "ok", text: "Your account and its data were deleted." })}
          />
        </>
      )}
      <div className="map-wrap" data-focus={focus ?? undefined}>
        <ManhattanMap
          selectedPoint={selectedPoint}
          area={result?.area}
          areaKey={result?.id}
          // Closed places leave the map; the panel still lists them.
          places={(result?.places ?? []).filter((p) => p.status !== "closed")}
          barriers={result?.barriers ?? []}
          view={view}
          grid={grid}
          weights={weights}
          gapCategory={gapCategory}
          flyTo={flyTo}
          onMapClick={handleMapClick}
        />
      </div>
    </div>
  );
}
