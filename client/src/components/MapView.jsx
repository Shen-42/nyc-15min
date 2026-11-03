import BoroughPicker from "./BoroughPicker";

// "Map view": your walk, the score map, or the gap finder (card 12), and a
// borough picker (card 15). Closed by default, like the other settings.
export const VIEWS = [
  { id: "walk", label: "Your walk" },
  { id: "heat", label: "Score map" },
  { id: "gaps", label: "Gap finder" },
];

export default function MapView({ view, onChange, borough, onPickBorough }) {
  const current = VIEWS.find((v) => v.id === view);
  return (
    <details className="needs">
      <summary className="needs__summary">
        Map view: <span className="needs__current">{current.label}</span>
      </summary>
      <div className="needs__body">
        <div className="needs__presets">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              className="needs__preset"
              aria-pressed={view === v.id}
              onClick={() => onChange(v.id)}
            >
              {v.label}
            </button>
          ))}
        </div>
        <p className="needs__note">
          These views cover the five boroughs, on foot, at any hour.
        </p>
        <p className="needs__label">Go to</p>
        <BoroughPicker borough={borough} onPick={onPickBorough} />
      </div>
    </details>
  );
}
