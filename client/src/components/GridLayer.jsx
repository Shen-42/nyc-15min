import { useEffect } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import { gridImage } from "../data/gridImage";
import { MANHATTAN_POLYGONS } from "../data/manhattan";

// The score map or gap finder (card 12), drawn as one smooth image built
// from the Manhattan grid (see data/gridImage.js). It sits in its own pane,
// above the map tiles and below the walk area and markers.
export default function GridLayer({ cells, cellM, blank, fill, valueFor, colorFor, sigma, opacity = 0.8 }) {
  const map = useMap();

  useEffect(() => {
    if (!map.getPane("grid")) {
      const pane = map.createPane("grid");
      pane.style.zIndex = 350; // above the tiles (200), below shapes (400)
      pane.style.pointerEvents = "none";
    }
    const { url, bounds } = gridImage({ cells, cellM, valueFor, colorFor, sigma, land: MANHATTAN_POLYGONS, blank, fill });
    const overlay = L.imageOverlay(url, bounds, { pane: "grid", opacity, interactive: false });
    overlay.addTo(map);
    return () => overlay.remove();
  }, [map, cells, cellM, blank, fill, valueFor, colorFor, sigma, opacity]);

  return null;
}
