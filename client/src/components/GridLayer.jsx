import { useEffect, useRef, useState } from "react";
import { useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import { gridImage } from "../data/gridImage";
import { LAND_POLYGONS } from "../data/city";

function viewOf(map) {
  const b = map.getBounds();
  return { south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast() };
}

// The score map or gap finder (cards 12 and 15), drawn as one smooth image
// built from the city grid (see data/gridImage.js) for the part of the map in
// view. It's drawn again whenever the map stops moving. It sits in its own
// pane, above the map tiles and below the walk area and markers.
export default function GridLayer({ cells, meta, blank, fill, valueFor, colorFor, sigma, opacity = 0.8 }) {
  const map = useMap();
  const [view, setView] = useState(() => viewOf(map));
  const shown = useRef(null);

  // moveend also follows every zoom.
  useMapEvents({ moveend: () => setView(viewOf(map)) });

  useEffect(() => {
    if (!map.getPane("grid")) {
      const pane = map.createPane("grid");
      pane.style.zIndex = 350; // above the tiles (200), below shapes (400)
      pane.style.pointerEvents = "none";
    }
    const image = gridImage({ cells, meta, view, valueFor, colorFor, sigma, land: LAND_POLYGONS, blank, fill });
    // Add the new image before taking the old one away, so nothing flickers.
    const overlay = image && L.imageOverlay(image.url, image.bounds, { pane: "grid", opacity, interactive: false });
    if (overlay) overlay.addTo(map);
    if (shown.current) shown.current.remove();
    shown.current = overlay;
  }, [map, view, cells, meta, blank, fill, valueFor, colorFor, sigma, opacity]);

  // Take the image away when the layer goes.
  useEffect(
    () => () => {
      if (shown.current) shown.current.remove();
      shown.current = null;
    },
    []
  );

  return null;
}
