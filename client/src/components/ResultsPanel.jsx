import { useLayoutEffect, useRef, useState } from "react";
import { CATEGORIES, verdict } from "../data/categories";
import { useMediaQuery } from "../hooks";
import CategoryRow from "./CategoryRow";
import LayerInfo from "./LayerInfo";
import MapView from "./MapView";
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
  sheet: sheetPosition,
  onSheetChange,
  weights,
  onWeightsChange,
  hour,
  onHourChange,
  timeLabel,
  mode,
  onModeChange,
  view,
  onViewChange,
  grid,
  gridError,
  gapCategory,
  onGapCategory,
}) {
  const loading = status === "loading";
  const categoryById = Object.fromEntries((result?.score.categories ?? []).map((c) => [c.category, c]));
  const sheet = useSheet(sheetPosition, onSheetChange);
  const open = sheetPosition === "open";

  return (
    <aside
      ref={sheet.panelRef}
      className={sheet.className}
      style={sheet.style}
      aria-label="Walk results"
    >
      {/* On phones, the top of the bottom sheet: swipe it up or down, or tap
          the handle, to move the sheet between hidden, peek, and open. */}
      <div className="panel__top" {...sheet.dragHandlers}>
      {sheet.mobile && (
        <button
          ref={sheet.handleRef}
          type="button"
          className="sheet-handle"
          aria-expanded={open}
          aria-controls="panel-more"
          onClick={sheet.onHandleClick}
        >
          <span className="sheet-handle__bar" aria-hidden="true" />
          <span className="visually-hidden">{HANDLE_LABELS[sheetPosition]}</span>
        </button>
      )}
      {/* What shows at "peek": the title and the score. Inert while hidden. */}
      <div ref={sheet.peekRef} className="panel__peek" inert={sheet.mobile && sheetPosition === "hidden"}>
      <h1 className="panel__title">NYC 15-Minute City Explorer</h1>

      {view !== "walk" && (
        <LayerInfo
          view={view}
          grid={grid}
          gridError={gridError}
          gapCategory={gapCategory}
          onGapCategory={onGapCategory}
          onBack={() => onViewChange("walk")}
        />
      )}

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
            {result.score.rank != null && ` Better than ${result.score.rank}% of Manhattan.`}
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
            {/* Card 12. Only for walking at any time, which is how the grid was scored. */}
            {result.score.rank != null && (
              <p className="score-summary__rank">Better than {result.score.rank}% of Manhattan.</p>
            )}
            <p className="score-summary__detail">
              {result.mode === "wheelchair" && "Within 15 minutes by wheelchair. "}
              The nearest of each is {result.score.proximity_minutes} minutes away on average.
              {timeLabel && ` Counting places open at ${timeLabel}.`}
              {result.mode === "wheelchair" && result.barriers.length > 0 && (
                <>
                  {" "}
                  {result.barriers.length === 1 ? "1 corner" : `${result.barriers.length} corners`} in reach{" "}
                  {result.barriers.length === 1 ? "has" : "have"} no listed curb ramp (
                  <span className="barrier-key" aria-hidden="true" />
                  <span className="visually-hidden">dark diamonds</span> on the map).
                </>
              )}
            </p>
          </div>
        </div>
      )}
      </div>
      </div>

      {/* Off screen on phones while the sheet is closed, and then inert, so Tab skips it. */}
      <div id="panel-more" className="panel__more" inert={sheet.mobile && !open}>
      {/* One group, so the settings stack without the panel's gap between them. */}
      <div className="settings">
        <TimeOfDay hour={hour} onChange={onHourChange} />
        <NeedsProfile weights={weights} onChange={onWeightsChange} mode={mode} onModeChange={onModeChange} />
        <MapView view={view} onChange={onViewChange} />
      </div>

      {result && (
        <div className="panel__results" aria-busy={loading}>
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
      </div>
    </aside>
  );
}

// What the handle does when tapped, for screen readers.
const HANDLE_LABELS = {
  hidden: "Show the score",
  peek: "Open settings and categories",
  open: "Close settings and categories",
};
// Tapping the handle moves the sheet one step: hidden to peek, peek to open,
// open back to peek. Swiping down from peek hides it.
const TAP_NEXT = { hidden: "peek", peek: "open", open: "peek" };

// How far a swipe must move, in pixels, before it counts as a swipe and not a tap.
const SWIPE_START_PX = 8;

// The bottom sheet on phones. It is always 85% of the screen tall and slides
// down to show less: all of it ("open"), just the title and score ("peek"),
// or just the handle ("hidden"). It follows the finger while dragging, then
// snaps to the nearest position in the direction of the swipe.
function useSheet(position, onChange) {
  const mobile = useMediaQuery("(max-width: 767px)");
  const panelRef = useRef(null);
  const handleRef = useRef(null);
  const peekRef = useRef(null);
  const drag = useRef(null);
  // When the last drag ended. The click that follows a drag isn't a tap.
  const dragEndedAt = useRef(0);
  // How far down the sheet slides for each position, measured.
  const [offsets, setOffsets] = useState({ open: 0, peek: 0, hidden: 0 });
  // The offset while a finger is on the sheet, or null.
  const [dragOffset, setDragOffset] = useState(null);

  useLayoutEffect(() => {
    if (!mobile) return;
    const measure = () => {
      const panel = panelRef.current;
      const handle = handleRef.current;
      const peek = peekRef.current;
      if (!panel || !handle || !peek) return;
      const height = panel.clientHeight;
      const handleHeight = handle.offsetHeight;
      setOffsets({
        open: 0,
        peek: Math.max(0, height - handleHeight - peek.offsetHeight - 8),
        hidden: Math.max(0, height - handleHeight),
      });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(peekRef.current);
    observer.observe(panelRef.current);
    return () => observer.disconnect();
  }, [mobile]);

  // Leaving "open" scrolls back to the top, so the score is what shows.
  useLayoutEffect(() => {
    if (mobile && position !== "open" && panelRef.current) panelRef.current.scrollTop = 0;
  }, [mobile, position]);

  const restOffset = offsets[position];
  const clamp = (y) => Math.min(offsets.hidden, Math.max(0, y));

  const dragHandlers = mobile
    ? {
        onPointerDown(event) {
          drag.current = { y: event.clientY, start: restOffset, moving: false, id: event.pointerId };
        },
        onPointerMove(event) {
          const d = drag.current;
          if (!d) return;
          const dy = event.clientY - d.y;
          if (!d.moving) {
            if (Math.abs(dy) < SWIPE_START_PX) return;
            d.moving = true;
            // Only now take over the pointer, so taps on buttons still work.
            event.currentTarget.setPointerCapture(d.id);
          }
          setDragOffset(clamp(d.start + dy));
        },
        onPointerUp(event) {
          const d = drag.current;
          drag.current = null;
          if (!d?.moving) return;
          const end = clamp(d.start + event.clientY - d.y);
          // The positions past the start in the direction of the swipe; of
          // those, the one nearest to where the finger let go.
          const ahead = Object.entries(offsets).filter(([, y]) => (end < d.start ? y < d.start : y > d.start));
          const [next] = ahead.sort((a, b) => Math.abs(a[1] - end) - Math.abs(b[1] - end))[0] ?? [position];
          dragEndedAt.current = performance.now();
          setDragOffset(null);
          onChange(next);
        },
        onPointerCancel() {
          drag.current = null;
          setDragOffset(null);
        },
      }
    : {};

  return {
    mobile,
    panelRef,
    handleRef,
    peekRef,
    dragHandlers,
    onHandleClick() {
      if (performance.now() - dragEndedAt.current < 300) return;
      onChange(TAP_NEXT[position]);
    },
    className: ["panel", mobile && `panel--${position}`, dragOffset !== null && "panel--dragging"]
      .filter(Boolean)
      .join(" "),
    // A CSS variable is the one inline style: the offset is measured, not designed.
    style: mobile ? { "--sheet-offset": `${dragOffset ?? restOffset}px` } : undefined,
  };
}
