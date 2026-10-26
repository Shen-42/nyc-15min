import { CATEGORIES, verdict } from "../data/categories";
import CategoryRow from "./CategoryRow";
import NeedsProfile from "./NeedsProfile";
import TimeOfDay from "./TimeOfDay";
import { formatHour } from "../data/time";

export default function ResultsPanel({
  status,
  result,
  message,
  serverDown,
  waking,
  focus,
  onFocus,
  expanded,
  onToggleExpanded,
  weights,
  onWeightsChange,
  hour,
  onHourChange,
  timeLabel,
}) {
  const loading = status === "loading";
  const categoryById = Object.fromEntries((result?.score.categories ?? []).map((c) => [c.category, c]));

  return (
    <aside className={`panel${expanded ? " panel--expanded" : ""}`} aria-label="Walk results">
      <h1 className="panel__title">NYC 15-Minute City Explorer</h1>

      {serverDown && (
        <p className="message message--error" role="alert">
          Can't reach the server. Reload the page in a minute to try again.
        </p>
      )}

      {waking && !serverDown && (
        <p className="message message--warn" role="status">
          Waking up the server…
        </p>
      )}

      {/* Screen readers announce changes in this region (search started, finished, failed). */}
      <div role="status" aria-live="polite">
        {!result && !loading && !message && (
          <p className="panel__intro">Pick a spot in Manhattan to see what you can reach on foot in 15 minutes.</p>
        )}
        {!result && loading && <p className="panel__intro">Finding everything within a 15-minute walk…</p>}
        {message && <p className={`message message--${message.kind}`}>{message.text}</p>}
        {result && (
          <p className="visually-hidden">
            Score {result.score.score} out of 100. {verdict(result.score.score)}
          </p>
        )}
      </div>

      {/* The score and the list are faded while a new search runs. The needs
          form sits between them, next to the score it changes, and never fades. */}
      {result && (
        <div className="panel__results" aria-busy={loading}>
          <div className="score-summary">
            <p className="score-summary__number" aria-hidden="true">
              {result.score.score}
            </p>
            <p className="score-summary__verdict" aria-hidden="true">
              {verdict(result.score.score)}
            </p>
            <p className="score-summary__detail">
              The nearest of each is {result.score.proximity_minutes} minutes away on average.
              {timeLabel && ` Counting places open at ${timeLabel}.`}
            </p>
          </div>
        </div>
      )}

      {/* One group, so the two settings stack without the panel's gap between them. */}
      <div className="settings">
        <TimeOfDay hour={hour} onChange={onHourChange} />
        <NeedsProfile weights={weights} onChange={onWeightsChange} />
      </div>

      {result && (
        <div className="panel__results" aria-busy={loading}>
          <button
            type="button"
            className="panel__toggle"
            aria-expanded={expanded}
            aria-controls="category-list"
            onClick={onToggleExpanded}
          >
            {expanded ? "Hide categories" : "Show categories"}
          </button>

          <ul className="category-list" id="category-list">
            {CATEGORIES.map((category) => (
              <CategoryRow
                key={category.id}
                category={category}
                result={categoryById[category.id]}
                selected={focus === category.id}
                onSelect={onFocus}
                hourLabel={timeLabel && formatHour(hour)}
              />
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}
