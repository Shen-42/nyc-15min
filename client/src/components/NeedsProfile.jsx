import { CATEGORIES } from "../data/categories";
import { IMPORTANCE, MODES, PRESETS, hasAnyWeight, matchingPreset } from "../data/profiles";

// "Needs: Default, walking". Closed, it's one line. Open, it shows how you
// get around and the presets, which is all most people change; the six
// importance menus are one more click away, under "Customize".
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
        Needs:{" "}
        <span className="needs__current">
          {preset ? preset.label : "Custom"}, {mode === "wheelchair" ? "wheelchair" : "walking"}
        </span>
        <span className="needs__change" aria-hidden="true">
          Change
        </span>
      </summary>

      <div className="needs__body">
        <div className="needs__presets" role="group" aria-label="Getting around">
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
        </div>

        <div className="needs__presets" role="group" aria-label="Presets">
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
        </div>

        <details className="needs__more">
          <summary className="needs__more-summary">Customize</summary>
          <fieldset className="needs__weights">
            <legend className="visually-hidden">How much each kind of place matters</legend>
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
        </details>
      </div>
    </details>
  );
}
