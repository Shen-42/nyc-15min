import { formatMinutes } from "./PlaceMarkers";

export default function CategoryRow({ category, result, selected, onSelect }) {
  const nearest = result?.nearest ?? [];
  const first = nearest[0];
  const detail = first
    ? `${first.name ?? "Unnamed"}, ${formatMinutes(first.minutes)}`
    : "None within 15 minutes";

  return (
    <li>
      <button
        type="button"
        className={`category-row cat-${category.id}`}
        aria-pressed={selected}
        onClick={() => onSelect(selected ? null : category.id)}
      >
        <span className="glyph" aria-hidden="true">
          {category.glyph}
        </span>
        <span>
          <span className="category-row__label">{category.label}</span>
          <span className="category-row__detail">{detail}</span>
        </span>
        <span className="category-row__score">
          <span className="meter" aria-hidden="true">
            {/* A CSS variable is the one inline style: the width is data. */}
            <span className="meter__fill" style={{ "--value": `${result?.score ?? 0}%` }} />
          </span>
          <span>
            {result?.score ?? 0}
            <span className="visually-hidden"> out of 100</span>
          </span>
        </span>
      </button>

      {selected && nearest.length > 1 && (
        <ol className="nearest-list" aria-label={`Nearest ${category.label.toLowerCase()}`}>
          {nearest.map((p, i) => (
            <li key={i}>
              {p.name ?? "Unnamed"}, {formatMinutes(p.minutes)}
            </li>
          ))}
        </ol>
      )}
    </li>
  );
}
