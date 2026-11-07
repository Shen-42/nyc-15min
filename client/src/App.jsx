import { useEffect, useRef, useState } from "react";
import { SLOW_REQUEST_MS, apiFetch } from "./api";
import { fetchArea } from "./area";
import ErrorBoundary from "./components/ErrorBoundary";
import { errorText, failureText, worthRetrying } from "./errors";
import AccountDialog from "./account/AccountDialog";
import AuthDialog from "./account/AuthDialog";
import { useAccount } from "./account/useAccount";
import { useAccountData } from "./account/useAccountData";
import CityMap from "./components/CityMap";
import MapView from "./components/MapView";
import ResultsPanel from "./components/ResultsPanel";
import { BOROUGHS, boroughAt, isInCityLimits } from "./data/city";
import { useGrid } from "./data/useGrid";
import { loadMode, loadWeights, saveMode, saveWeights, weightsToQuery } from "./data/profiles";
import { atQuery, formatHour, nycNow } from "./data/time";
import { addRecent, describeSpot, loadRecent } from "./data/recent";

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
  // { kind: "warn" | "error", text, retry? } or null. With retry, the
  // message shows a "Try again" button that calls it (card 14).
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
  // The part of the city in view ({ bounds, center }), and the borough at its
  // middle, which the score map and gap finder describe (card 15).
  const [mapView, setMapView] = useState(null);
  const [borough, setBorough] = useState("Manhattan");
  const { grid, boroughGrid, gridError } = useGrid(view, mapView, borough);
  // Where the map should fit to when a borough is picked.
  const [fitTo, setFitTo] = useState(null);
  // Accounts (card 13): who is signed in, their saved places, and which
  // dialog is open. authReason says why sign-in was asked for, or is null.
  const account = useAccount();
  const saved = useAccountData({ account, weights, mode, setWeights, setMode });
  const [authOpen, setAuthOpen] = useState(false);
  const [authReason, setAuthReason] = useState(null);
  const [accountOpen, setAccountOpen] = useState(false);
  // Where the map should move to, e.g. when a saved place is picked.
  const [flyTo, setFlyTo] = useState(null);
  // A short note shown on the map at a spot that was turned away ("That's
  // in Central Park"), as well as in the panel: { point, text, key } or null.
  const [mapNote, setMapNote] = useState(null);
  // True while the browser looks up where the visitor is.
  const [locating, setLocating] = useState(false);
  // The last few spots looked at, for the address box (heuristic 6).
  const [recent, setRecent] = useState(loadRecent);
  // A name for the spot being searched, when it came with one (an address,
  // a saved place). Map clicks are named from what the search finds.
  const spotLabel = useRef(null);
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
  // time someone picks a spot. Run again by "Try again" if it failed.
  function checkHealth() {
    setServerDown(false);
    const slow = setTimeout(() => setWaking(true), SLOW_REQUEST_MS);
    apiFetch("/api/health")
      .then((res) => setServerDown(!res.ok))
      .catch(() => setServerDown(true))
      .finally(() => {
        clearTimeout(slow);
        setWaking(false);
      });
  }

  useEffect(checkHealth, []); // eslint-disable-line react-hooks/exhaustive-deps

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

  function handleMapMove(next) {
    setMapView(next);
    const here = boroughAt(next.center);
    if (here) setBorough(here.name);
  }

  // The score map and gap finder explain themselves in the panel, so on
  // phones a hidden sheet comes up far enough to show that.
  function changeView(next) {
    setView(next);
    if (next !== "walk") setSheet((s) => (s === "hidden" ? "peek" : s));
  }

  function pickBorough(name) {
    const b = BOROUGHS.find((x) => x.name === name);
    setBorough(name);
    setFitTo({ bounds: b.bounds, key: Date.now() });
  }

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
        const text = await errorText(res, `Couldn't update the score (error ${res.status}).`);
        const retry = worthRetrying(res.status) ? rescore : undefined;
        setMessage({ kind: retry ? "error" : "warn", text, retry });
        return;
      }
      const data = await res.json();
      if (!current()) return;
      setMessage(null);
      setResult((r) =>
        r?.id === searchId ? { ...r, places: data.amenities, score: data.score, barriers: data.barriers ?? [] } : r
      );
    } catch (err) {
      if (current()) setMessage({ kind: "error", text: failureText(err), retry: rescore });
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
    // fetchArea tries the area twice before giving up (card 14).
    const areaRequest = fetchArea(query).then(
      (data) => ({ data }),
      () => ({ failed: true })
    );

    try {
      const res = await apiFetch(`/api/places?${placesQuery(point)}`);
      if (requestId !== latestRequest.current) return;
      if (!res.ok) {
        // 422: the server turned the click away (water, a park, no path
        // nearby) and says why. 429: too many searches in a minute. Those
        // won't change by trying again; a server error might.
        const text = await errorText(res);
        const retry = worthRetrying(res.status) ? () => findWalkingArea(point) : undefined;
        // In a park or the water, or far from any street: offer a way out.
        const action =
          res.headers.get("X-Suggest") === "nearest-street"
            ? { label: "Use the nearest street", onClick: () => goToNearestStreet(point) }
            : undefined;
        setResult(null);
        setMessage({ kind: retry ? "error" : "warn", text, retry, action });
        if (!retry) setMapNote({ point, text, key: requestId });
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
        // True until the shaded area arrives or fails; the map shows a
        // pulsing ring at the spot meanwhile.
        areaPending: true,
      });
      setServerDown(false);
      setStatus("done");
      setRecent((list) =>
        addRecent(list, {
          label: spotLabel.current ?? describeSpot(data.amenities, data.borough),
          lat: point[0],
          lng: point[1],
        })
      );
    } catch (err) {
      if (requestId !== latestRequest.current) return;
      // fetch() throws when the server can't be reached at all, or when the
      // request timed out.
      setMessage({ kind: "error", text: failureText(err), retry: () => findWalkingArea(point) });
      setStatus("done");
      return;
    } finally {
      clearTimeout(slow);
      if (requestId === latestRequest.current) setWaking(false);
    }

    showArea(requestId, query, await areaRequest);
  }

  // Draws the shaded area when it arrives, or says it couldn't be drawn.
  // The score and places are already showing, so this is only a warning.
  function showArea(requestId, query, { data, failed }) {
    if (requestId !== latestRequest.current) return;
    setResult((current) => (current?.id === requestId ? { ...current, areaPending: !failed && !data } : current));
    if (failed) {
      setMessage({
        kind: "warn",
        text: "Couldn't draw the walking area. The score is still correct.",
        retry: () => {
          setMessage(null);
          fetchArea(query).then(
            (again) => showArea(requestId, query, { data: again }),
            () => showArea(requestId, query, { failed: true })
          );
        },
      });
      return;
    }
    if (!data) return;
    setResult((current) =>
      current?.id === requestId
        ? { ...current, area: { type: "Feature", properties: {}, geometry: data.area }, areaPending: false }
        : current
    );
  }

  function openSignIn(reason = null) {
    account.setNotice(null);
    setAuthReason(reason);
    setAuthOpen(true);
  }

  // history: "push" adds the spot to the browser's history (a click),
  // "replace" swaps the current entry (opening a shared link), "none" leaves
  // it (the back button, which has already moved).
  function goToPlace(place, { history = "push" } = {}) {
    const point = [place.lat, place.lng];
    setFlyTo({ point, key: Date.now() });
    handleMapClick(point, { history, label: place.label ?? place.name ?? null });
  }

  // "Use the nearest street": after a click in a park or the water, search
  // from the nearest street point the server would accept.
  async function goToNearestStreet(point) {
    setMessage({ kind: "warn", text: "Finding the nearest street…" });
    try {
      const res = await apiFetch(`/api/nearest-street?lat=${point[0]}&lng=${point[1]}`);
      if (!res.ok) return setMessage({ kind: "warn", text: await errorText(res) });
      const street = await res.json();
      goToPlace({ lat: street.lat, lng: street.lng });
    } catch (err) {
      setMessage({ kind: "error", text: failureText(err), retry: () => goToNearestStreet(point) });
    }
  }

  function handleMapClick(point, { history = "push", label = null } = {}) {
    spotLabel.current = label;
    setFocus(null);
    setMapNote(null);
    setView("walk"); // a click asks about one spot, so go back to your walk
    setSheet((s) => (s === "hidden" ? "peek" : s)); // and its score should show
    // Rivers and bays inside the city go to the server too, which names them.
    if (isInCityLimits(point)) {
      writeUrlPoint(point, history);
      setSelectedPoint(point);
      findWalkingArea(point);
    } else {
      clearSpot();
      const text = "That's outside NYC. Pick a spot in the city.";
      setMessage({
        kind: "warn",
        text,
        action: {
          label: "Go to Manhattan",
          onClick: () => {
            setMessage(null);
            setMapNote(null);
            pickBorough("Manhattan");
          },
        },
      });
      setMapNote({ point, text, key: Date.now() });
    }
  }

  function clearSpot() {
    latestRequest.current++; // ignore any search still in flight
    pointRef.current = null;
    setSelectedPoint(null);
    setResult(null);
    setStatus("idle");
    setMessage(null);
  }

  // The spot is in the page's address (?lat=40.758&lng=-73.9855), so a
  // result can be shared or bookmarked, and the back button goes to the
  // previous spot. On opening the page, a spot in the address is searched.
  useEffect(() => {
    const start = readUrlPoint();
    if (start) goToPlace({ lat: start[0], lng: start[1] }, { history: "replace" });
    const onPop = () => {
      const point = readUrlPoint();
      if (point) goToPlace({ lat: point[0], lng: point[1] }, { history: "none" });
      else clearSpot();
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // "Use my location": only for people inside the city.
  function locateMe() {
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false);
        const point = [position.coords.latitude, position.coords.longitude];
        if (isInCityLimits(point)) goToPlace({ lat: point[0], lng: point[1] });
        else setMessage({ kind: "warn", text: "You're outside NYC. Search an address or pick a spot on the map." });
      },
      (err) => {
        setLocating(false);
        setMessage({
          kind: "warn",
          text:
            err.code === err.PERMISSION_DENIED
              ? "Location is turned off for this site. Search an address instead."
              : "Couldn't find your location. Search an address instead.",
        });
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 }
    );
  }

  return (
    <div className="app">
      <ErrorBoundary name="panel" className="panel">
      <ResultsPanel
        status={status}
        result={result}
        message={message}
        serverDown={serverDown}
        onRetryHealth={checkHealth}
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
        grid={grid}
        borough={borough}
        boroughGrid={boroughGrid}
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
        onPickAddress={goToPlace}
        onUseLocation={locateMe}
        locating={locating}
        recent={recent}
      />
      </ErrorBoundary>
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
        <MapView view={view} onChange={changeView} onPickBorough={pickBorough} />
        <ErrorBoundary name="map">
        <CityMap
          selectedPoint={selectedPoint}
          area={result?.area}
          areaKey={result?.id}
          // A pulsing ring at the spot until the shaded area is drawn.
          pending={status === "loading" || Boolean(result?.areaPending)}
          areaLabel={result?.mode === "wheelchair" ? "15 minutes by wheelchair" : "15-minute walk"}
          note={mapNote}
          onNoteClose={(key) => setMapNote((n) => (n?.key === key ? null : n))}
          // Closed places leave the map; the panel still lists them.
          places={(result?.places ?? []).filter((p) => p.status !== "closed")}
          barriers={result?.barriers ?? []}
          view={view}
          grid={grid}
          weights={weights}
          gapCategory={gapCategory}
          flyTo={flyTo}
          fitTo={fitTo}
          onViewChange={handleMapMove}
          onMapClick={handleMapClick}
        />
        </ErrorBoundary>
      </div>
    </div>
  );
}

// The spot in the page's address, as [lat, lng], or null.
function readUrlPoint() {
  const params = new URLSearchParams(window.location.search);
  const lat = Number.parseFloat(params.get("lat"));
  const lng = Number.parseFloat(params.get("lng"));
  return Number.isFinite(lat) && Number.isFinite(lng) ? [lat, lng] : null;
}

// Five decimals is about a meter: short links, and the same spot.
function writeUrlPoint([lat, lng], how) {
  if (how === "none") return;
  const url = `${window.location.pathname}?lat=${lat.toFixed(5)}&lng=${lng.toFixed(5)}`;
  if (how === "replace") window.history.replaceState(null, "", url);
  else window.history.pushState(null, "", url);
}
