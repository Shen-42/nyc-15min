import { useEffect, useMemo, useRef, useState } from "react";
// MapLibre draws the base map from vector tiles (card 15) and everything on
// it, and handles dragging and zooming. It zooms smoothly and continuously,
// drawing each frame on the graphics card, instead of stretching a picture
// and redrawing once the zoom ends.
import { AttributionControl, LngLatBounds, Map as MapLibreMap, NavigationControl, Popup, setWorkerUrl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// MapLibre parses tiles in a web worker, which it looks for next to its own
// file. Vite bundles that file elsewhere, so give it the worker's address.
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";

setWorkerUrl(maplibreWorkerUrl);
import { CITY_BOUNDS, CITY_CENTER, CITY_OUTLINE, OUTER_RING } from "../data/city";
import BarrierMarkers from "./BarrierMarkers";
import GridLayer from "./GridLayer";
import MapMarker, { MapContext, useMap } from "./MapMarker";
import { CATEGORY_BY_ID } from "../data/categories";
import { cellScore, heatColor, hexToRgb, inPark, isGap } from "../data/grid";
import { smoothstep } from "../data/gridImage";
import PlaceMarkers from "./PlaceMarkers";

// The base map: Stadia Maps' "OSM Bright" style (green parks, blue water,
// colored roads) as vector tiles. Stadia sends the streets, parks, and labels
// as shapes and the browser draws them, so zooming redraws the map at once
// instead of waiting for new pictures of every level. One download also
// serves several zoom levels. Free for non-commercial use. The style names
// its own credit (Stadia Maps, OpenMapTiles, OpenStreetMap), which MapLibre
// shows in the corner.
//
// On the live site, Stadia allows requests by checking the site's domain
// (registered in the Stadia dashboard), so no key is needed. On localhost,
// requests without a key are heavily rate-limited, so a free key in
// client/.env.local (VITE_STADIA_API_KEY=...) is added when present.
// .env.local is not committed, so the key stays off GitHub.
const STADIA_KEY = import.meta.env.VITE_STADIA_API_KEY;
const STYLE_URL =
  "https://tiles.stadiamaps.com/styles/osm_bright.json" + (STADIA_KEY ? `?api_key=${STADIA_KEY}` : "");

// MapLibre takes [lng, lat]; the app's points are [lat, lng].
const lngLat = ([lat, lng]) => [lng, lat];

// The gap finder's best spot: a star, a shape no other marker uses.
const STAR_HTML = '<span class="best-spot__shape" aria-hidden="true">★</span>';
// A ring that pulses at the clicked spot while its results load, so the
// map shows the click was heard. Animated in map.css (not with reduced motion).
const PENDING_HTML = '<span class="pending-spot__ring"></span>';

// The grey over everything outside the city: the whole world, with the
// city's outline cut out of it.
const MASK = {
  type: "Feature",
  properties: {},
  geometry: { type: "Polygon", coordinates: [OUTER_RING, ...CITY_OUTLINE].map((ring) => ring.map(lngLat)) },
};
const EMPTY = { type: "FeatureCollection", features: [] };

// The walk color, from styles/tokens.css, for the shapes MapLibre draws.
const walkColor = () => getComputedStyle(document.documentElement).getPropertyValue("--color-walk").trim();

// The box around a GeoJSON shape.
function boundsOf(feature) {
  const bounds = new LngLatBounds();
  const add = (coords) => (typeof coords[0] === "number" ? bounds.extend(coords) : coords.forEach(add));
  add(feature.geometry.coordinates);
  return bounds;
}

// Moves the map to a point, e.g. a saved place (card 13). key changes on
// every request, so picking the same place twice still moves the map.
function FlyTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo({ center: lngLat(target.point), zoom: Math.max(map.getZoom(), 14), duration: 600 });
  }, [map, target]);
  return null;
}

// When a new walking area arrives, makes sure all of it is in view: on
// phones, in the part of the map above the results sheet and below the map
// buttons. Moves only if part of it is hidden, so a click doesn't jolt a
// map that already shows the whole walk.
function FitArea({ area, areaKey }) {
  const map = useMap();
  useEffect(() => {
    if (!area) return;
    const container = map.getContainer();
    const box = container.getBoundingClientRect();
    const app = container.closest(".app");
    const toolbar = parseFloat(getComputedStyle(app ?? container).getPropertyValue("--toolbar-space")) || 0;
    // On phones the sheet lies over the bottom of the map; elsewhere the
    // panel sits beside it and covers nothing.
    const sheet = app?.querySelector(".panel");
    const covered = window.matchMedia("(max-width: 767px)").matches && sheet
      ? Math.max(0, box.bottom - sheet.getBoundingClientRect().top)
      : 0;
    if (covered > box.height * 0.6) return; // sheet open: little map to fit into
    const padding = { top: toolbar + 8, left: 16, right: 16, bottom: covered + 16 };
    const bounds = boundsOf(area);
    const visible = new LngLatBounds(
      map.unproject([padding.left, box.height - padding.bottom]),
      map.unproject([box.width - padding.right, padding.top])
    );
    if (visible.contains(bounds.getSouthWest()) && visible.contains(bounds.getNorthEast())) return;
    map.fitBounds(bounds, { padding, maxZoom: 15, duration: 600 });
  }, [map, areaKey]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

// A small key for the shaded area (heuristic 2: say what the grey means): in
// the bottom left corner, where maps keep their legends, or on phones, where
// the results sheet covers the bottom, at the top left under the map buttons.
function AreaKey({ label }) {
  const map = useMap();
  useEffect(() => {
    const box = document.createElement("div");
    box.className = "maplibregl-ctrl map-key";
    box.innerHTML = '<span class="map-key__swatch" aria-hidden="true"></span><span class="map-key__label"></span>';
    box.querySelector(".map-key__label").textContent = `Shaded: ${label}`;
    const control = { onAdd: () => box, onRemove: () => box.remove() };
    const phone = window.matchMedia("(max-width: 767px)").matches;
    map.addControl(control, phone ? "top-left" : "bottom-left");
    return () => map.removeControl(control);
  }, [map, label]);
  return null;
}

// Moves the map to a borough picked in the panel (card 15).
function FitTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.fitBounds(target.bounds.map(lngLat), { duration: 600, padding: 20 });
  }, [map, target]);
  return null;
}

// Tells the app what part of the city is in view, when the map stops moving
// and once at the start, so it can load the grid for those boroughs.
function ViewWatcher({ onViewChange }) {
  const map = useMap();
  const latest = useRef(onViewChange);
  latest.current = onViewChange;
  useEffect(() => {
    const report = () => {
      const b = map.getBounds();
      const c = map.getCenter();
      latest.current({
        bounds: [
          [b.getSouth(), b.getWest()],
          [b.getNorth(), b.getEast()],
        ],
        center: [c.lat, c.lng],
      });
    };
    report();
    map.on("moveend", report);
    return () => map.off("moveend", report);
  }, [map]);
  return null;
}

// Runs onMapClick with [lat, lng] whenever the map is clicked.
function ClickHandler({ onMapClick }) {
  const map = useMap();
  const latest = useRef(onMapClick);
  latest.current = onMapClick;
  useEffect(() => {
    const onClick = (e) => latest.current([e.lngLat.lat, e.lngLat.lng]);
    map.on("click", onClick);
    return () => map.off("click", onClick);
  }, [map]);
  return null;
}

// Your walk's shaded area and starting dot, drawn by MapLibre above the grey
// mask and below the markers. Empty when there's nothing to show.
function WalkShapes({ area, point }) {
  const map = useMap();
  useEffect(() => {
    const color = walkColor();
    map.addSource("walk-area", { type: "geojson", data: EMPTY });
    map.addLayer({ id: "walk-area", type: "fill", source: "walk-area", paint: { "fill-color": color, "fill-opacity": 0.12 } });
    map.addLayer({ id: "walk-area-edge", type: "line", source: "walk-area", paint: { "line-color": color, "line-width": 2 } });
    map.addSource("start-point", { type: "geojson", data: EMPTY });
    map.addLayer({
      id: "start-point",
      type: "circle",
      source: "start-point",
      paint: { "circle-radius": 8, "circle-color": color, "circle-stroke-color": "#fff", "circle-stroke-width": 3 },
    });
    return () => {
      for (const id of ["start-point", "walk-area-edge", "walk-area"]) map.removeLayer(id);
      map.removeSource("start-point");
      map.removeSource("walk-area");
    };
  }, [map]);
  useEffect(() => {
    map.getSource("walk-area").setData(area ?? EMPTY);
  }, [map, area]);
  useEffect(() => {
    map.getSource("start-point").setData(point ? { type: "Point", coordinates: lngLat(point) } : EMPTY);
  }, [map, point]);
  return null;
}

// Why a click was turned away, at the spot itself (the panel says it too).
// Closing it (✕, or a click elsewhere) clears it, unless a newer one has replaced it.
function Note({ note, onClose }) {
  const map = useMap();
  const latest = useRef(onClose);
  latest.current = onClose;
  useEffect(() => {
    const popup = new Popup({ className: "map-note", maxWidth: "260px" })
      .setLngLat(lngLat(note.point))
      .setText(note.text)
      .addTo(map);
    const closed = () => latest.current(note.key);
    popup.on("close", closed);
    return () => {
      popup.off("close", closed);
      popup.remove();
    };
  }, [map, note]);
  return null;
}

// Colors for the markers come from styles/map.css, by class name.
export default function CityMap({
  selectedPoint,
  area,
  areaKey,
  places,
  barriers = [],
  view = "walk",
  grid = null,
  weights,
  gapCategory,
  flyTo = null,
  fitTo = null,
  pending = false,
  areaLabel = "15-minute walk",
  note = null,
  onNoteClose = () => {},
  onViewChange = () => {},
  onMapClick,
}) {
  // The map, once its style has loaded; nothing is drawn on it before then.
  const container = useRef(null);
  const [map, setMap] = useState(null);
  useEffect(() => {
    const m = new MapLibreMap({
      container: container.current,
      style: STYLE_URL,
      center: lngLat(CITY_CENTER),
      // MapLibre's zoom levels are one less than Leaflet's for the same view.
      zoom: 12,
      minZoom: 10,
      maxZoom: 17,
      maxBounds: CITY_BOUNDS.map(lngLat),
      // A flat map: no tilting or turning it with right-drag or two fingers.
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      attributionControl: false,
    });
    m.touchZoomRotate.disableRotation();
    // Faster than MapLibre's defaults (1/450 for a mouse wheel, 1/100 for a
    // trackpad), which feel slow. A wheel notch zooms about 0.7 levels, near
    // the one level per notch of other map sites. A trackpad pinch scales
    // the map as far as the fingers spread: Chrome reports a pinch as
    // 100 × ln(scale), and 1/50 turns that back into the same scale.
    m.scrollZoom.setWheelZoomRate(1 / 70);
    m.scrollZoom.setZoomRate(1 / 50);
    // The credit in the top right corner, above the toolbar (map.css), so the
    // sheet on phones never covers it. Kept on one line, never folded into a button.
    m.addControl(new AttributionControl({ compact: false }), "top-right");
    m.addControl(new NavigationControl({ showCompass: false }), "top-left");
    m.on("load", () => {
      m.addSource("outside-mask", { type: "geojson", data: MASK });
      m.addLayer({ id: "outside-mask", type: "fill", source: "outside-mask", paint: { "fill-color": "#333", "fill-opacity": 0.35 } });
      m.addLayer({ id: "outside-mask-edge", type: "line", source: "outside-mask", paint: { "line-color": "#666", "line-width": 1 } });
      setMap(m);
    });
    return () => {
      setMap(null);
      // After the shapes and markers on it have taken themselves off.
      queueMicrotask(() => m.remove());
    };
  }, []);

  // What the score map or gap finder draws (card 12): a value for each grid
  // square of the boroughs loaded so far (card 15), and a color for each value. data/gridImage.js smooths the values
  // into a gradient. Park cells have no value, since nobody lives there.
  const layer = useMemo(() => {
    if (!grid || view === "walk") return null;
    const categories = grid.meta.categories;
    if (view === "heat") {
      // Parks have no value of their own (nobody lives there), and are
      // filled in from the blocks around them so the gradient has no holes.
      return {
        valueFor: (cell) => (inPark(cell, categories) ? null : cellScore(cell, categories, weights)),
        colorFor: (score) => [...heatColor(score), 1],
        sigma: 1.2,
        fill: true,
        blank: grid.water,
      };
    }
    // Gaps take their category's color, the same as its markers. The value
    // is the share of nearby cells that are gaps, so lone squares stay faint
    // and clusters show solid.
    const rgb = hexToRgb(getComputedStyle(document.documentElement).getPropertyValue(`--cat-${gapCategory}`).trim());
    // A gap in a park means nothing, so parks stay blank here.
    return {
      valueFor: (cell) => (inPark(cell, categories) ? null : isGap(cell, categories, gapCategory) ? 1 : 0),
      colorFor: (share) => (share < 0.1 ? null : [...rgb, 0.9 * smoothstep(0.1, 0.45, share)]),
      sigma: 0.9,
      blank: [...grid.parks, ...grid.water],
    };
  }, [grid, view, weights, gapCategory]);

  const walking = view === "walk";
  // Each loaded borough's best spot for a new place.
  const stars = view === "gaps" && grid ? grid.best[gapCategory] : [];

  return (
    <div ref={container} className="map">
      {map && (
        <MapContext.Provider value={map}>
          {layer && <GridLayer cells={grid.cells} meta={grid.meta} {...layer} />}

          {stars.map(({ borough, spot }) => (
            <MapMarker
              key={borough}
              position={[spot.lat, spot.lng]}
              className="best-spot"
              html={STAR_HTML}
              size={30}
              tooltipOffset={16}
              tooltip={`Best spot for a new ${CATEGORY_BY_ID[gapCategory].one}${spot.near ? `, near ${spot.near}` : ""}`}
            />
          ))}

          {/* Your walk's layers. Hidden in the score map and gap finder, which cover the whole city. */}
          <WalkShapes area={walking ? area : null} point={walking ? selectedPoint : null} />
          {walking && <BarrierMarkers barriers={barriers} />}
          {walking && <PlaceMarkers places={places} />}

          {walking && selectedPoint && pending && (
            <MapMarker position={selectedPoint} className="pending-spot" html={PENDING_HTML} size={44} />
          )}
          {walking && <FitArea area={area} areaKey={area ? areaKey : null} />}
          {walking && area && <AreaKey label={areaLabel} />}

          {note && <Note key={note.key} note={note} onClose={onNoteClose} />}

          <FlyTo target={flyTo} />
          <FitTo target={fitTo} />
          <ViewWatcher onViewChange={onViewChange} />
          <ClickHandler onMapClick={onMapClick} />
        </MapContext.Provider>
      )}
    </div>
  );
}
