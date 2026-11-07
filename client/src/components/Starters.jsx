// Before the first search, under the address box: "Use my location", for
// people in the city who'd rather not type an address. Only shown where the
// browser can look up a location.
export default function Starters({ onUseLocation, locating }) {
  if (!("geolocation" in navigator)) return null;
  return (
    <button type="button" className="link-button starters__location" onClick={onUseLocation} disabled={locating}>
      {locating ? "Finding you…" : "Use my location"}
    </button>
  );
}
