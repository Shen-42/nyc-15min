import { CATEGORIES, CATEGORY_BY_ID } from "../data/categories";
import { HEAT_GRADIENT, HEAT_LEGEND } from "../data/grid";

// The heading, legend, and way back for the score map and gap finder (card 12).
// Shown at the top of the panel while one of them is on.
export default function LayerInfo({ view, grid, gridError, gapCategory, onGapCategory, onBack }) {
  const title = view === "heat" ? "Score map" : "Gap finder";

  return (
    <section className="layer" aria-labelledby="layer-title">
      <h2 id="layer-title" className="layer__title">
        {title}
      </h2>

      {/* A failure to load shows with the panel's other messages (card 14). */}
      {!grid && !gridError && <p className="needs__note">Loading map data…</p>}

      {grid && view === "heat" && (
        <>
          <p className="layer__text">
            Scores across Manhattan for a 15-minute walk, weighted by your needs. Parks show the scores of
            the blocks around them. Click a street for details.
          </p>
          {/* A gradient bar with numbers under it and words at both ends, so
              the colors never have to be told apart alone. */}
          <figure className="legend">
            <div className="legend__bar" style={{ "--gradient": HEAT_GRADIENT }} aria-hidden="true" />
            <div className="legend__ticks" aria-hidden="true">
              {HEAT_LEGEND.ticks.map((t) => (
                <span key={t}>{t}</span>
              ))}
            </div>
            <figcaption className="legend__ends">
              <span>
                <span className="visually-hidden">Dark purple, 0: </span>
                {HEAT_LEGEND.low}
              </span>
              <span>
                <span className="visually-hidden">Yellow, 100: </span>
                {HEAT_LEGEND.high}
              </span>
            </figcaption>
          </figure>
        </>
      )}

      {grid && view === "gaps" && <GapText grid={grid} categoryId={gapCategory} onCategory={onGapCategory} />}

      <button type="button" className="needs__preset layer__back" onClick={onBack}>
        Back to your walk
      </button>
    </section>
  );
}

function GapText({ grid, categoryId, onCategory }) {
  const category = CATEGORY_BY_ID[categoryId];
  const gap = grid.gaps[categoryId];
  const total = grid.meta.outside_park_count ?? grid.meta.cell_count;
  const best = gap.best;
  const where = best && (best.near ? `near ${best.near}` : `at ${best.lat.toFixed(4)}, ${best.lng.toFixed(4)}`);

  return (
    <>
      <label className="needs__row layer__select">
        <span className={`glyph cat-${categoryId}`} aria-hidden="true">
          {category.glyph}
        </span>
        <span className="needs__label">Show gaps in</span>
        <select className="needs__select" value={categoryId} onChange={(e) => onCategory(e.target.value)}>
          {CATEGORIES.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </label>

      {gap.cells === 0 ? (
        <p className="layer__text">No gaps: every part of Manhattan has a {category.one} within a 15-minute walk.</p>
      ) : (
        <>
          <p className="layer__text">
            <strong>
              {gap.cells.toLocaleString()} of {total.toLocaleString()}
            </strong>{" "}
            areas (100 m squares, parks excluded) have no {category.one} within a 15-minute walk. They're
            shaded on the map.
          </p>
          {best && (
            <p className="layer__text">
              A new {category.one} {where} would serve <strong>{best.fixes.toLocaleString()}</strong> of them
              (★ on the map).
            </p>
          )}
        </>
      )}
    </>
  );
}
