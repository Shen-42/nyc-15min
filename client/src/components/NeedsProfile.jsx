import { CATEGORIES } from "../data/categories";
import { IMPORTANCE, MODES, PRESETS, hasAnyWeight, matchingPreset } from "../data/profiles";

// "Your needs": how you get around, then a preset, then how much each kind
// of place matters. A native <details> keeps it out of the way until opened.
export default function NeedsProfile({ weights, onChange, mode, onModeChange }) {
  const preset = matchingPreset(weights);

  function setWeight(id, value) {
    const next = { ...weights, [id]: value };
    // At least one category has to count, or there's nothing to score.
    if (hasAnyWeight(next)) onChange(next);
  }

  return (
    <details className="needs">
      <summary className="needs__summary">
        Your needs:{" "}
        <span className="needs__current">
          {preset ? preset.label : "Custom"}
          {mode === "wheelchair" && ", wheelchair"}
        </span>
      </summary>

      <div className="needs__body">
        <fieldset className="needs__presets">
          <legend className="needs__legend">Getting around</legend>
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              className="needs__preset"
              aria-pressed={mode === m.id}
              onClick={() => onModeChange(m.id)}
            >
              {m.label}
            </button>
          ))}
        </fieldset>

        <fieldset className="needs__presets">
          <legend className="needs__legend">Presets</legend>
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              className="needs__preset"
              aria-pressed={preset?.id === p.id}
              onClick={() => onChange(p.weights)}
            >
              {p.label}
            </button>
          ))}
        </fieldset>

        <fieldset className="needs__weights">
          <legend className="needs__legend">Importance</legend>
          {CATEGORIES.map((category) => {
            const value = weights[category.id];
            const onlyOneLeft = value > 0 && Object.values(weights).filter((w) => w > 0).length === 1;
            return (
              <label key={category.id} className={`needs__row cat-${category.id}`}>
                <span className="glyph" aria-hidden="true">
                  {category.glyph}
                </span>
                <span className="needs__label">{category.label}</span>
                <select
                  className="needs__select"
                  value={value}
                  onChange={(event) => setWeight(category.id, Number(event.target.value))}
                >
                  {IMPORTANCE.map((level) => (
                    <option key={level.value} value={level.value} disabled={level.value === 0 && onlyOneLeft}>
                      {level.label}
                    </option>
                  ))}
                </select>
              </label>
            );
          })}
        </fieldset>

        <p className="needs__note">Saved in this browser.</p>
      </div>
    </details>
  );
}
