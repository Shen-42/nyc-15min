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
  const detail = first
    ? `${placeName(first)}, ${formatMinutes(first.minutes)}`
    : hourLabel && closedCount
      ? `None open within 15 minutes`
      : "None within 15 minutes";

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
        <span>
          <span className="category-row__label">{category.label}</span>
          <span className="category-row__detail">{detail}</span>
          {hourLabel && closedCount > 0 && (
            <span className="category-row__detail">
              {openCount} of {openCount + closedCount} open at {hourLabel}
            </span>
          )}
        </span>
        {counted ? (
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
        ) : (
          <span className="category-row__off">Not counted</span>
        )}
      </button>

      {selected && (nearest.length > 1 || closed.length > 0) && (
        <div className="nearest">
          {nearest.length > 0 && (
            <ol className="nearest-list" aria-label={`Nearest ${category.label.toLowerCase()}`}>
              {nearest.map((p, i) => (
                <li key={i}>
                  {placeName(p)}, {formatMinutes(p.minutes)}
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
                    {p.name ?? "Unnamed"}, {formatMinutes(p.minutes)}
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
// has no hours for the place.
function placeName(place) {
  const name = place.name ?? "Unnamed";
  return place.status === "unknown" ? `${name} (hours unknown)` : name;
}
