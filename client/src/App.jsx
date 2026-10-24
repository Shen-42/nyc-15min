import { useEffect, useRef, useState } from "react";
import { SLOW_REQUEST_MS, apiFetch } from "./api";
import ManhattanMap from "./components/ManhattanMap";
import ResultsPanel from "./components/ResultsPanel";
import { isInManhattan } from "./data/manhattan";

const MINUTES = 15;

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
  // On phones, whether the category list is open in the bottom sheet.
  const [expanded, setExpanded] = useState(false);
  // True while a request has taken long enough that the server is probably waking up.
  const [waking, setWaking] = useState(false);
  // Counts requests so a slow old response can't replace a newer one.
  const latestRequest = useRef(0);

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

  async function findWalkingArea(point) {
    const requestId = ++latestRequest.current;
    setStatus("loading");
    setMessage(null);
    const slow = setTimeout(() => {
      if (requestId === latestRequest.current) setWaking(true);
    }, SLOW_REQUEST_MS);
    try {
      const res = await apiFetch(`/api/reachable?lat=${point[0]}&lng=${point[1]}&minutes=${MINUTES}`);
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
      setResult({
        id: requestId, // tells the map a new area arrived
        area: { type: "Feature", properties: {}, geometry: data.area },
        places: data.amenities,
        score: data.score,
      });
      setServerDown(false);
      setStatus("done");
    } catch {
      if (requestId !== latestRequest.current) return;
      // fetch() throws when the server can't be reached at all.
      setServerDown(true);
      setStatus("done");
    } finally {
      clearTimeout(slow);
      if (requestId === latestRequest.current) setWaking(false);
    }
  }

  function handleMapClick(point) {
    setFocus(null);
    if (isInManhattan(point)) {
      setSelectedPoint(point);
      findWalkingArea(point);
    } else {
      latestRequest.current++; // ignore any search still in flight
      setSelectedPoint(null);
      setResult(null);
      setStatus("idle");
      setMessage({ kind: "warn", text: "Only Manhattan is available for now. Pick a spot on the island." });
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
        expanded={expanded}
        onToggleExpanded={() => setExpanded((open) => !open)}
      />
      <div className="map-wrap" data-focus={focus ?? undefined}>
        <ManhattanMap
          selectedPoint={selectedPoint}
          area={result?.area}
          areaKey={result?.id}
          places={result?.places ?? []}
          onMapClick={handleMapClick}
        />
      </div>
    </div>
  );
}
