import { useState } from "react";
import { formatHour, nycNow } from "../data/time";

// "Open: Any time". Closed, it's one line, like "Needs". Open, it has three
// buttons, Any time, Now, and Pick a time, and the hour slider only shows
// for Pick a time. hour is null for Any time, when opening hours aren't checked.
export default function TimeOfDay({ hour, onChange }) {
  const now = nycNow();
  const [picking, setPicking] = useState(hour !== null && hour !== now.hour);

  function choose(nextPicking, nextHour) {
    setPicking(nextPicking);
    onChange(nextHour);
  }

  return (
    <details className="needs time">
      <summary className="needs__summary">
        Open:{" "}
        <span className="needs__current">{hour === null ? "Any time" : `at ${formatHour(hour)}`}</span>
        <span className="needs__change" aria-hidden="true">
          Change
        </span>
      </summary>

      <div className="needs__body">
        <div className="time__buttons" role="group" aria-label="Count places open at">
          <button type="button" className="time__button" aria-pressed={hour === null} onClick={() => choose(false, null)}>
            Any time
          </button>
          <button
            type="button"
            className="time__button"
            aria-pressed={hour !== null && !picking}
            onClick={() => choose(false, nycNow().hour)}
          >
            Now
          </button>
          <button
            type="button"
            className="time__button"
            aria-pressed={hour !== null && picking}
            onClick={() => choose(true, hour ?? now.hour)}
          >
            Pick a time
          </button>
        </div>

        {hour !== null && picking && (
          <div>
            {/* A native range input: arrow keys, Home, and End work without extra code. */}
            <input
              type="range"
              className="time__slider"
              min="0"
              max="23"
              step="1"
              value={hour}
              aria-label="Hour of day, New York time"
              aria-valuetext={formatHour(hour)}
              onChange={(event) => onChange(Number(event.target.value))}
            />
            <div className="time__ends" aria-hidden="true">
              <span>12 am</span>
              <span>11 pm</span>
            </div>
          </div>
        )}

        {hour !== null && (
          <p className="needs__note">
            NYC time. Places with unknown hours (?) count as open.
          </p>
        )}
      </div>
    </details>
  );
}
