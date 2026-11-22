import { useEffect, useRef, useState } from "react";
import { useMap } from "./MapMarker";
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
// view. It goes above the base map and below the grey mask (CityMap.jsx).
//
// Drawing takes a moment, so it happens as rarely as possible: the image
// covers twice the view, and it's only drawn again when the map moves past
// it or zooms in two levels or more (when it would start to look soft).
// During a zoom the map stretches the image that's there, so there's never
// an empty map while the new one is drawn.
export default function GridLayer({ cells, meta, blank, fill, valueFor, colorFor, sigma, opacity = 0.8 }) {
  const map = useMap();
  // The area and zoom of the image on the map, or null before the first one.
  const [drawn, setDrawn] = useState(null);
  // The id of the image's source and layer on the map, and a count for the next one.
  const shown = useRef(null);
  const count = useRef(0);

  // moveend also follows every zoom. A new image is needed only if the
  // view has left the one on the map, or zoomed well into it.
  useEffect(() => {
    const onMoveEnd = () => {
      const view = viewOf(map);
      setDrawn((current) =>
        current && covers(current, view) && view.zoom < current.zoom + 2 ? current : { ...padded(view), zoom: view.zoom }
      );
    };
    map.on("moveend", onMoveEnd);
    return () => map.off("moveend", onMoveEnd);
  }, [map]);

  useEffect(() => {
    const area = drawn ?? { ...padded(viewOf(map)), zoom: map.getZoom() };
    const image = gridImage({ cells, meta, view: area, valueFor, colorFor, sigma, land: LAND_POLYGONS, blank, fill });
    // The canvas goes on the map as it is, its corners pinned to the area.
    // The new one goes on before the old one comes off, so nothing flickers.
    const old = shown.current;
    shown.current = null;
    if (image) {
      const id = `grid-${count.current++}`;
      const [[south, west], [north, east]] = image.bounds;
      map.addSource(id, {
        type: "canvas",
        canvas: image.canvas,
        animate: false,
        coordinates: [
          [west, north],
          [east, north],
          [east, south],
          [west, south],
        ],
      });
      map.addLayer(
        { id, type: "raster", source: id, paint: { "raster-opacity": opacity, "raster-fade-duration": 0 } },
        "outside-mask"
      );
      shown.current = id;
    }
    if (old) {
      map.removeLayer(old);
      map.removeSource(old);
    }
  }, [map, drawn, cells, meta, blank, fill, valueFor, colorFor, sigma, opacity]);

  // Take the image away when the layer goes.
  useEffect(
    () => () => {
      if (shown.current) {
        map.removeLayer(shown.current);
        map.removeSource(shown.current);
      }
      shown.current = null;
    },
    [map]
  );

  return null;
}
