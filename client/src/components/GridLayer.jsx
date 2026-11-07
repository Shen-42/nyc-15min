import { useEffect, useRef, useState } from "react";
import { useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import { gridImage } from "../data/gridImage";
import { LAND_POLYGONS } from "../data/city";

// How much more than the view to draw, on each side, as a share of the
// view's width and height. Half on each side makes the image twice as wide
// and tall as the view, so panning half a screen or zooming out one level
// shows color that's already drawn instead of an empty edge.
const MARGIN = 0.5;

function viewOf(map) {
  const b = map.getBounds();
  return { south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast(), zoom: map.getZoom() };
}

function padded(view) {
  const dLat = (view.north - view.south) * MARGIN;
  const dLng = (view.east - view.west) * MARGIN;
  return { south: view.south - dLat, west: view.west - dLng, north: view.north + dLat, east: view.east + dLng };
}

const covers = (outer, inner) =>
  outer.south <= inner.south && outer.north >= inner.north && outer.west <= inner.west && outer.east >= inner.east;

// The score map or gap finder (cards 12 and 15), drawn as one smooth image
// built from the city grid (see data/gridImage.js) for the area around the
// view. It sits in its own pane, above the map tiles and below the walk area
// and markers.
//
// Drawing takes a moment, so it happens as rarely as possible: the image
// covers twice the view, and it's only drawn again when the map moves past
// it or zooms in two levels or more (when it would start to look soft).
// During a zoom Leaflet stretches the image that's there, so there's never
// an empty map while the new one is drawn.
export default function GridLayer({ cells, meta, blank, fill, valueFor, colorFor, sigma, opacity = 0.8 }) {
  const map = useMap();
  // The area and zoom of the image on the map, or null before the first one.
  const [drawn, setDrawn] = useState(null);
  const shown = useRef(null);

  // moveend also follows every zoom. A new image is needed only if the
  // view has left the one on the map, or zoomed well into it.
  useMapEvents({
    moveend: () => {
      const view = viewOf(map);
      setDrawn((current) =>
        current && covers(current, view) && view.zoom < current.zoom + 2 ? current : { ...padded(view), zoom: view.zoom }
      );
    },
  });

  useEffect(() => {
    if (!map.getPane("grid")) {
      const pane = map.createPane("grid");
      pane.style.zIndex = 350; // above the tiles (200), below shapes (400)
      pane.style.pointerEvents = "none";
    }
    const area = drawn ?? { ...padded(viewOf(map)), zoom: map.getZoom() };
    const image = gridImage({ cells, meta, view: area, valueFor, colorFor, sigma, land: LAND_POLYGONS, blank, fill });
    // Leaflet's SVG overlay places any element over an area of the map and
    // stretches it along with zooms; here the element is the canvas itself.
    // The new one goes on before the old one comes off, so nothing flickers.
    const overlay = image && L.svgOverlay(image.canvas, image.bounds, { pane: "grid", opacity, interactive: false });
    if (overlay) overlay.addTo(map);
    if (shown.current) shown.current.remove();
    shown.current = overlay;
  }, [map, drawn, cells, meta, blank, fill, valueFor, colorFor, sigma, opacity]);

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
