import { BOROUGHS } from "../data/city";

// Moves the map to a borough (card 15). The pressed button is the borough at
// the middle of the map, which the score map and gap finder describe.
export default function BoroughPicker({ borough, onPick }) {
  return (
    <div className="needs__presets" role="group" aria-label="Go to a borough">
      {BOROUGHS.map((b) => (
        <button
          key={b.name}
          type="button"
          className="needs__preset"
          aria-pressed={borough === b.name}
          onClick={() => onPick(b.name)}
        >
          {b.name}
        </button>
      ))}
    </div>
  );
}

// "Better than 70% of Brooklyn and 64% of the city." from the API's rank.
export function rankText(rank) {
  if (!rank) return null;
  if (rank.borough == null) return `Better than ${rank.city}% of the city.`;
  return `Better than ${rank.borough}% of ${rank.name} and ${rank.city}% of the city.`;
}
