import { BOROUGHS } from "../data/city";

// "Go to…": moves the map to a borough (card 15). It always reads "Go to…",
// so picking the borough already in view still moves back to its middle.
export default function BoroughPicker({ onPick }) {
  return (
    <select
      className="map-select"
      value=""
      aria-label="Go to a borough"
      onChange={(event) => event.target.value && onPick(event.target.value)}
    >
      <option value="" disabled>
        Go to…
      </option>
      {BOROUGHS.map((b) => (
        <option key={b.name} value={b.name}>
          {b.name}
        </option>
      ))}
    </select>
  );
}

// "Better than 70% of Brooklyn, 64% of NYC" from the API's rank.
export function rankText(rank) {
  if (!rank) return null;
  if (rank.borough == null) return `Better than ${rank.city}% of NYC`;
  return `Better than ${rank.borough}% of ${rank.name}, ${rank.city}% of NYC`;
}
