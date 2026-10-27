// "Map view": your walk, the score map, or the gap finder (card 12).
// Closed by default, like the other settings.
export const VIEWS = [
  { id: "walk", label: "Your walk" },
  { id: "heat", label: "Score map" },
  { id: "gaps", label: "Gap finder" },
];

export default function MapView({ view, onChange }) {
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
          These views cover all of Manhattan, on foot, at any hour.
        </p>
      </div>
    </details>
  );
}
