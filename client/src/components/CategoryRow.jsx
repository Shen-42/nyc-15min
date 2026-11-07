import { formatMinutes } from "./PlaceMarkers";

// hourLabel: "9 pm" when a time is chosen (card 10), otherwise null.
export default function CategoryRow({ category, result, selected, onSelect, hourLabel }) {
  const nearest = result?.nearest ?? [];
  const closed = result?.closed ?? [];
  const closedCount = result?.closed_count ?? 0;
  const openCount = result?.count ?? 0;
  const first = nearest[0];
  // Older responses have no "counted"; treat those as counted.
  const counted = result?.counted !== false;
  // One line: "H Mart · 6 min". The full list opens with the row.
  const detail = first
    ? `${placeName(first, category)} · ${Math.max(1, Math.round(first.minutes))} min`
    : hourLabel && closedCount
      ? "None open within 15 min"
      : "None within 15 min";

  return (
    <li>
      <button
        type="button"
        className={`category-row cat-${category.id}${counted ? "" : " category-row--off"}`}
        aria-pressed={selected}
        onClick={() => onSelect(selected ? null : category.id)}
      >
        <span className="glyph" aria-hidden="true">
          {category.glyph}
        </span>
        {/* Label and nearest place on one line; a long name is cut with "…"
            (the title shows it whole on hover). */}
        <span className="category-row__text" title={`${category.label}: ${detail}`}>
          <span className="category-row__line">
            <span className="category-row__label">{category.label}</span>{" "}
            <span className="category-row__detail">{detail}</span>
          </span>
          {hourLabel && closedCount > 0 && (
            <span className="category-row__open">
              {openCount} of {openCount + closedCount} open at {hourLabel}
            </span>
          )}
        </span>
        {counted ? (
          <span className="category-row__score">
            {result?.score ?? 0}
            <span className="visually-hidden"> out of 100</span>
          </span>
        ) : (
          <span className="category-row__off">Off</span>
        )}
      </button>

      {selected && (nearest.length > 1 || closed.length > 0) && (
        <div className="nearest">
          {nearest.length > 0 && (
            <ol className="nearest-list" aria-label={`Nearest ${category.label.toLowerCase()}`}>
              {nearest.map((p, i) => (
                <li key={i}>
                  {placeName(p, category)}, {formatMinutes(p.minutes)}
                </li>
              ))}
            </ol>
          )}
          {closed.length > 0 && (
            <>
              <p className="nearest-list__heading">Closed at {hourLabel}</p>
              <ul className="nearest-list nearest-list--closed">
                {closed.map((p, i) => (
                  <li key={i}>
                    {placeName({ ...p, status: null }, category)}, {formatMinutes(p.minutes)}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </li>
  );
}

// "Duane Reade (hours unknown)" when a time is chosen and OpenStreetMap
// has no hours for the place. With no name listed, what it is: "A pharmacy".
function placeName(place, category) {
  const name = place.name ?? `A ${category.one}`;
  return place.status === "unknown" ? `${name} (hours unknown)` : name;
}
