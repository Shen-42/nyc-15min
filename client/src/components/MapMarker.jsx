import { createContext, useContext, useEffect, useRef } from "react";
import { Marker, Popup } from "maplibre-gl";

// The MapLibre map, for the pieces drawn on it (CityMap.jsx provides it once
// the map's style has loaded, so layers can be added straight away).
export const MapContext = createContext(null);
export const useMap = () => useContext(MapContext);

// Runs handler on every one of the map's `type` events, always the latest
// handler, without taking the listener off and on again when it changes.
export function useMapEvent(type, handler) {
  const map = useMap();
  const latest = useRef(handler);
  latest.current = handler;
  useEffect(() => {
    const listener = (e) => latest.current(e);
    map.on(type, listener);
    return () => map.off(type, listener);
  }, [map, type]);
}

// An HTML marker at [lat, lng]: an element with className and html, size
// pixels square, centered on the spot. With a tooltip, it shows that text in
// a small box above it on hover (or a tap, on phones). Markers with a
// tooltip catch their clicks, so clicking one doesn't search from there;
// the others let clicks through to the map.
export default function MapMarker({ position, className, html, size, tooltip, tooltipOffset = 12, onTop = false }) {
  const map = useMap();
  const [lat, lng] = position;
  useEffect(() => {
    const el = document.createElement("div");
    el.className = className;
    el.innerHTML = html;
    el.style.width = el.style.height = `${size}px`;
    if (onTop) el.style.zIndex = 1;
    const marker = new Marker({ element: el }).setLngLat([lng, lat]).addTo(map);

    let tip = null;
    const show = () => {
      tip?.remove();
      tip = new Popup({ closeButton: false, closeOnClick: false, anchor: "bottom", offset: tooltipOffset, className: "place-tooltip" })
        .setLngLat([lng, lat])
        .setText(tooltip)
        .addTo(map);
    };
    const hide = () => {
      tip?.remove();
      tip = null;
    };
    if (tooltip) {
      el.addEventListener("mouseenter", show);
      el.addEventListener("mouseleave", hide);
      el.addEventListener("click", (e) => e.stopPropagation());
    } else {
      el.style.pointerEvents = "none";
    }
    return () => {
      hide();
      marker.remove();
    };
  }, [map, lat, lng, className, html, size, tooltip, tooltipOffset, onTop]);
  return null;
}
