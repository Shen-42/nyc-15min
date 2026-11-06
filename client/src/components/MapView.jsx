import { useLayoutEffect, useRef } from "react";
import BoroughPicker from "./BoroughPicker";

// The map's own controls, floating over its top edge: your walk, the score
// map, or the gap finder (card 12), and a menu to move to a borough (card
// 15). They change the map, not the score, so they sit on the map, the way
// map apps place layer switches, and the panel keeps to the results.
export const VIEWS = [
  { id: "walk", label: "Your walk" },
  { id: "heat", label: "Score map" },
  { id: "gaps", label: "Gap finder" },
];

export default function MapView({ view, onChange, onPickBorough }) {
  const ref = useRef(null);

  // Leaflet's zoom buttons sit in the map's top left corner. Move them
  // below the toolbar, however many rows it wraps to.
  useLayoutEffect(() => {
    const toolbar = ref.current;
    const wrap = toolbar?.parentElement;
    if (!wrap) return;
    const measure = () => wrap.style.setProperty("--toolbar-space", `${toolbar.offsetTop + toolbar.offsetHeight}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(toolbar);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className="map-toolbar">
      <div className="segmented" role="group" aria-label="Map view">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            className="segmented__button"
            aria-pressed={view === v.id}
            onClick={() => onChange(v.id)}
          >
            {v.label}
          </button>
        ))}
      </div>
      <BoroughPicker onPick={onPickBorough} />
    </div>
  );
}
