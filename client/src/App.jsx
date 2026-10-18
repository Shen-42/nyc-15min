import { useEffect, useState } from "react";

// Card 1 check: the React app calls the back end's /api/health route
// and shows whether it answered. Card 2 replaces this with the map.
export default function App() {
  const [status, setStatus] = useState("checking");
  const [detail, setDetail] = useState("");

  useEffect(() => {
    fetch("/api/health")
      .then((res) => {
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setStatus("ok");
        setDetail(`Server says: ${data.status} (version ${data.version})`);
      })
      .catch((err) => {
        setStatus("error");
        setDetail(`Could not reach the server: ${err.message}`);
      });
  }, []);

  return (
    <main className="app">
      <h1>NYC 15-Minute City Explorer</h1>
      <p className={`status status-${status}`}>
        {status === "checking" ? "Checking server..." : detail}
      </p>
    </main>
  );
}
