import { useEffect, useRef, useState } from "react";
import ManhattanMap from "./components/ManhattanMap";
import { isInManhattan } from "./data/manhattan";

const MINUTES = 15;

export default function App() {
  const [serverStatus, setServerStatus] = useState("checking");
  const [selectedPoint, setSelectedPoint] = useState(null);
  const [notice, setNotice] = useState("Click anywhere in Manhattan.");
  // status: "idle" | "loading" | "done" | "not-written" | "error"
  const [search, setSearch] = useState({ status: "idle" });
  // Counts requests so a slow old response can't replace a newer one.
  const latestRequest = useRef(0);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => {
        if (!res.ok) throw new Error();
        setServerStatus("ok");
      })
      .catch(() => setServerStatus("error"));
  }, []);

  async function findWalkingArea(point) {
    const requestId = ++latestRequest.current;
    setSearch({ status: "loading" });
    try {
      const res = await fetch(`/api/reachable?lat=${point[0]}&lng=${point[1]}&minutes=${MINUTES}`);
      if (requestId !== latestRequest.current) return;
      if (res.status === 501) {
        setSearch({ status: "not-written" });
        return;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        // 422 means the server turned the click away and says why.
        throw new Error(res.status === 422 ? body.detail : `Search failed: ${body.detail ?? res.status}`);
      }
      const data = await res.json();
      if (requestId !== latestRequest.current) return;
      setSearch({
        status: "done",
        // The server sends the walking area as a GeoJSON geometry.
        area: { type: "Feature", properties: {}, geometry: data.area },
        reachedCount: data.points.length,
        startDistance: data.start.distance_m,
      });
    } catch (err) {
      if (requestId !== latestRequest.current) return;
      // fetch() throws a TypeError when the server can't be reached at all.
      const message = err instanceof TypeError ? "Search failed: can't reach the server." : err.message;
      setSearch({ status: "error", message });
    }
  }

  function handleMapClick(point) {
    if (isInManhattan(point)) {
      setSelectedPoint(point);
      setNotice("");
      findWalkingArea(point);
    } else {
      latestRequest.current++; // ignore any search still in flight
      setSelectedPoint(null);
      setSearch({ status: "idle" });
      setNotice("Only Manhattan is available for now.");
    }
  }

  return (
    <div className="layout">
      <aside className="panel">
        <h1>NYC 15-Minute City Explorer</h1>

        {selectedPoint ? (
          <dl className="coords">
            <dt>Latitude</dt>
            <dd>{selectedPoint[0].toFixed(5)}</dd>
            <dt>Longitude</dt>
            <dd>{selectedPoint[1].toFixed(5)}</dd>
          </dl>
        ) : (
          <p className="notice">{notice}</p>
        )}

        {search.status === "loading" && <p className="notice">Finding your {MINUTES}-minute walk...</p>}
        {search.status === "done" && (
          <p className="notice">
            Shaded: everywhere you can walk in {MINUTES} minutes ({search.reachedCount.toLocaleString()} street
            points).
          </p>
        )}
        {search.status === "not-written" && (
          <p className="notice warn">
            The {MINUTES}-minute search isn't written yet. Fill in <code>reachable_within</code> in{" "}
            <code>server/graph.py</code>.
          </p>
        )}
        {search.status === "error" && <p className="notice warn">{search.message}</p>}

        <p className={`server server-${serverStatus}`}>
          {serverStatus === "checking" && "Checking server..."}
          {serverStatus === "ok" && "Server connected"}
          {serverStatus === "error" && "Server not reachable. Is uvicorn running?"}
        </p>
      </aside>

      <ManhattanMap
        selectedPoint={selectedPoint}
        area={search.status === "done" ? search.area : null}
        onMapClick={handleMapClick}
      />
    </div>
  );
}
