import { formatHour, nycNow } from "../data/time";

// "Time: Open at 9 pm": a slider for the hour, plus Any time and Now.
// hour is null for Any time, when opening hours aren't checked. Closed by
// default, like "Your needs", so the panel stays short.
export default function TimeOfDay({ hour, onChange }) {
  const now = nycNow();
  const value = hour ?? now.hour;

  return (
    <details className="needs time">
      <summary className="needs__summary">
        Time: <span className="needs__current">{hour === null ? "Any time" : `Open at ${formatHour(hour)}`}</span>
      </summary>

      <div className="needs__body">
        <div className="time__buttons">
          <button type="button" className="time__button" aria-pressed={hour === null} onClick={() => onChange(null)}>
            Any time
          </button>
          <button
            type="button"
            className="time__button"
            aria-pressed={hour === now.hour}
            onClick={() => onChange(nycNow().hour)}
          >
            Now
          </button>
        </div>

        <div>
          {/* A native range input: arrow keys, Home, and End work without extra code. */}
          <input
            type="range"
            className={`time__slider${hour === null ? " time__slider--idle" : ""}`}
            min="0"
            max="23"
            step="1"
            value={value}
            aria-label="Hour of day, New York time"
            aria-valuetext={formatHour(value)}
            onChange={(event) => onChange(Number(event.target.value))}
          />
          <div className="time__ends" aria-hidden="true">
            <span>12 am</span>
            <span>11 pm</span>
          </div>
        </div>

        <p className="needs__note">
          {hour === null
            ? "All places count. Move the slider to count only those open at that hour."
            : `${now.weekday}, New York time. Places without listed hours (?) count as open.`}
        </p>
      </div>
    </details>
  );
}
