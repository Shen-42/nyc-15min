import { useEffect, useMemo, useRef, useState } from "react";
import { failureText } from "../errors";
import { BOROUGHS, boxesOverlap } from "./city";
import { combineGrids, loadBoroughGrid, loadGridIndex } from "./grid";

// The city grid (cards 12 and 15), one file per borough, loaded for the
// boroughs in view once the score map or gap finder opens. Each file is 70 to
// 250 KB compressed, and is loaded once.
//   view: "walk", "heat", or "gaps". Nothing loads on "walk".
//   mapView: the part of the city in view ({ bounds, center }), or null.
//   borough: the borough the score map and gap finder describe.
// Returns every loaded borough's grid combined, the borough's own grid, and
// { text, retry } if loading failed.
export function useGrid(view, mapView, borough) {
  // gridIndex says which file holds each borough; grids holds the loaded ones by slug.
  const [gridIndex, setGridIndex] = useState(null);
  const [grids, setGrids] = useState({});
  const loadingGrids = useRef(new Set());
  const [gridError, setGridError] = useState(null);
  // Bumped by "Try again" to load the grid again after a failure.
  const [gridAttempt, setGridAttempt] = useState(0);

  useEffect(() => {
    if (view === "walk" || !mapView) return;
    setGridError(null);
    const fail = (err) => setGridError({ text: err instanceof TypeError ? failureText(err) : err.message });
    if (!gridIndex) {
      loadGridIndex().then(setGridIndex, fail);
      return;
    }
    if (!Object.keys(gridIndex.files ?? {}).length) {
      setGridError({ text: "This map isn't available yet." });
      return;
    }
    for (const b of BOROUGHS) {
      const path = gridIndex.files?.[b.slug];
      if (!path || grids[b.slug] || loadingGrids.current.has(b.slug)) continue;
      if (!boxesOverlap(b.allBounds, mapView.bounds)) continue;
      loadingGrids.current.add(b.slug);
      loadBoroughGrid(path)
        .then((g) => setGrids((loaded) => ({ ...loaded, [b.slug]: g })), fail)
        .finally(() => loadingGrids.current.delete(b.slug));
    }
  }, [view, mapView, gridIndex, grids, gridAttempt]);

  const grid = useMemo(() => combineGrids(grids), [grids]);
  const boroughGrid = grids[BOROUGHS.find((b) => b.name === borough)?.slug] ?? null;
  return {
    grid,
    boroughGrid,
    gridError: gridError && { ...gridError, retry: () => setGridAttempt((n) => n + 1) },
  };
}
