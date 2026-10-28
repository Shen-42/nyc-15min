import { useEffect, useState } from "react";
import { errorText } from "./errors";

const ROUTES = [
  ["/api/places", "Scores"],
  ["/api/area", "Areas"],
];

// Admins only (card 13): the last 7 days of searches, saved-data totals,
// and a button that starts the monthly data refresh now. The server checks
// the role on every request; this panel is only shown to admins as well.
export default function AdminPanel({ authFetch }) {
  const [usage, setUsage] = useState(null);
  const [error, setError] = useState(null);
  const [refresh, setRefresh] = useState(null); // { kind, text, link? }
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    authFetch("/api/admin/usage")
      .then(async (res) => (res.ok ? setUsage(await res.json()) : setError(await errorText(res))))
      .catch(() => setError("Couldn't load usage. Try again in a minute."));
  }, [authFetch]);

  async function startRefresh() {
    setBusy(true);
    setRefresh(null);
    try {
      const res = await authFetch("/api/admin/refresh", { method: "POST" });
      if (res.ok) {
        const body = await res.json();
        setRefresh({ kind: "ok", text: "Data refresh started. It takes about 15 minutes.", link: body.runs });
      } else {
        setRefresh({ kind: "error", text: await errorText(res) });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="account__section" aria-labelledby="admin-title">
      <h3 id="admin-title" className="account__heading">
        Admin
      </h3>
      {error && <p className="message message--error">{error}</p>}
      {!usage && !error && <p className="field__hint">Loading…</p>}
      {usage && (
        <>
          <table className="usage">
            <caption className="field__hint">Searches in the last 7 days</caption>
            <thead>
              <tr>
                <th scope="col">Day</th>
                {ROUTES.map(([, label]) => (
                  <th key={label} scope="col">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {usage.days.map((day) => (
                <tr key={day.date}>
                  <th scope="row">{day.date.slice(5)}</th>
                  {ROUTES.map(([route]) => (
                    <td key={route}>{(day.counts[route] ?? 0).toLocaleString()}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="field__hint">
            {usage.totals.profiles.toLocaleString()} saved needs profiles,{" "}
            {usage.totals.saved_places.toLocaleString()} saved places.
          </p>
        </>
      )}
      <button type="button" className="button" onClick={startRefresh} disabled={busy}>
        {busy ? "Starting…" : "Start data refresh"}
      </button>
      {refresh && (
        <p className={`message message--${refresh.kind === "ok" ? "ok" : "error"}`} role="status">
          {refresh.text}{" "}
          {refresh.link && (
            <a href={refresh.link} target="_blank" rel="noreferrer">
              Follow it on GitHub
            </a>
          )}
        </p>
      )}
    </section>
  );
}
