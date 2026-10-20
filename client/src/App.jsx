import { useEffect, useState } from "react";
import ManhattanMap from "./components/ManhattanMap";
import { isInManhattan } from "./data/manhattan";

export default function App() {
  const [serverStatus, setServerStatus] = useState("checking");
  const [selectedPoint, setSelectedPoint] = useState(null);
  const [notice, setNotice] = useState("Click anywhere in Manhattan.");

  // Same health check as card 1, now a small status line.
  useEffect(() => {
    fetch("/api/health")
      .then((res) => {
        if (!res.ok) throw new Error();
        setServerStatus("ok");
      })
      .catch(() => setServerStatus("error"));
  }, []);

  function handleMapClick(point) {
    if (isInManhattan(point)) {
      setSelectedPoint(point);
      setNotice("");
    } else {
      setSelectedPoint(null);
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

        <p className={`server server-${serverStatus}`}>
          {serverStatus === "checking" && "Checking server..."}
          {serverStatus === "ok" && "Server connected"}
          {serverStatus === "error" && "Server not reachable. Is uvicorn running?"}
        </p>
      </aside>

      <ManhattanMap selectedPoint={selectedPoint} onMapClick={handleMapClick} />
    </div>
  );
}
