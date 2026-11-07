import { useEffect, useMemo } from "react";
import {
  AttributionControl,
  CircleMarker,
  GeoJSON,
  MapContainer,
  Marker,
  Polygon,
  Popup,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
// MapLibre draws the base map from vector tiles (card 15), and the plugin
// puts it inside Leaflet as one more layer, under the walk area and markers.
import { setWorkerUrl } from "maplibre-gl";
import { maplibreGL } from "@maplibre/maplibre-gl-leaflet";
import "maplibre-gl/dist/maplibre-gl.css";
// MapLibre parses tiles in a web worker, which it looks for next to its own
// file. Vite bundles that file elsewhere, so give it the worker's address.
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";

setWorkerUrl(maplibreWorkerUrl);
import { CITY_BOUNDS, CITY_CENTER, CITY_OUTLINE, OUTER_RING } from "../data/city";
import BarrierMarkers from "./BarrierMarkers";
import GridLayer from "./GridLayer";
import { CATEGORY_BY_ID } from "../data/categories";
import { cellScore, heatColor, hexToRgb, inPark, isGap } from "../data/grid";
import { smoothstep } from "../data/gridImage";
import PlaceMarkers from "./PlaceMarkers";

// The base map: Stadia Maps' "OSM Bright" style (green parks, blue water,
// colored roads) as vector tiles. Stadia sends the streets, parks, and labels
// as shapes and the browser draws them, so zooming redraws the map at once
// instead of waiting for new pictures of every level. One download also
// serves several zoom levels. Free for non-commercial use.
//
// On the live site, Stadia allows requests by checking the site's domain
// (registered in the Stadia dashboard), so no key is needed. On localhost,
// requests without a key are heavily rate-limited, so a free key in
// client/.env.local (VITE_STADIA_API_KEY=...) is added when present.
// .env.local is not committed, so the key stays off GitHub.
const STADIA_KEY = import.meta.env.VITE_STADIA_API_KEY;
const STYLE_URL =
  "https://tiles.stadiamaps.com/styles/osm_bright.json" + (STADIA_KEY ? `?api_key=${STADIA_KEY}` : "");
const MAP_CREDIT =
  '&copy; <a href="https://stadiamaps.com/attribution/" target="_blank">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/" target="_blank">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>';

// Adds the vector base map to the Leaflet map, and removes it on unmount.
// Leaflet still handles dragging and zooming; MapLibre only draws.
function VectorBaseMap() {
  const map = useMap();
  useEffect(() => {
    const layer = maplibreGL({
      style: STYLE_URL,
      // The plugin turns MapLibre's own credit box off and hands this text
      // to Leaflet's, so the credit stays in one place.
      attributionControl: { customAttribution: MAP_CREDIT },
      interactive: false,
    }).addTo(map);
    return () => layer.remove();
  }, [map]);
  return null;
}

// The gap finder's best spot: a star, a shape no other marker uses.
const STAR_ICON = L.divIcon({
  className: "best-spot",
  html: '<span class="best-spot__shape" aria-hidden="true">★</span>',
  iconSize: [30, 30],
  iconAnchor: [15, 15],
});

// Moves the map to a point, e.g. a saved place (card 13). key changes on
// every request, so picking the same place twice still moves the map.
function FlyTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo(target.point, Math.max(map.getZoom(), 15), { duration: 0.6 });
  }, [map, target]);
  return null;
}

// A ring that pulses at the clicked spot while its results load, so the
// map shows the click was heard. Animated in map.css (not with reduced motion).
const PENDING_ICON = L.divIcon({
  className: "pending-spot",
  html: '<span class="pending-spot__ring"></span>',
  iconSize: [44, 44],
  iconAnchor: [22, 22],
});

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
    const topLeft = [16, toolbar + 8];
    const bottomRight = [16, covered + 16];
    const bounds = L.geoJSON(area).getBounds();
    const visible = L.latLngBounds(
      map.containerPointToLatLng([topLeft[0], box.height - bottomRight[1]]),
      map.containerPointToLatLng([box.width - bottomRight[0], topLeft[1]])
    );
    if (visible.contains(bounds)) return;
    map.flyToBounds(bounds, { paddingTopLeft: topLeft, paddingBottomRight: bottomRight, maxZoom: 16, duration: 0.6 });
  }, [map, areaKey]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

// Moves the map to a borough picked in the panel (card 15).
function FitTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyToBounds(target.bounds, { duration: 0.6, padding: [20, 20] });
  }, [map, target]);
  return null;
}

// Tells the app what part of the city is in view, when the map stops moving
// and once at the start, so it can load the grid for those boroughs.
function ViewWatcher({ onViewChange }) {
  const map = useMap();
  const report = () => {
    const b = map.getBounds();
    const c = map.getCenter();
    onViewChange({
      bounds: [
        [b.getSouth(), b.getWest()],
        [b.getNorth(), b.getEast()],
      ],
      center: [c.lat, c.lng],
    });
  };
  useMapEvents({ moveend: report });
  useEffect(report, []); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

// react-leaflet hook: runs our function whenever the map is clicked.
function ClickHandler({ onMapClick }) {
  useMapEvents({
    click(e) {
      onMapClick([e.latlng.lat, e.latlng.lng]);
    },
  });
  return null;
}

// Colors for the shapes below come from styles/map.css, by class name.
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
  note = null,
  onNoteClose = () => {},
  onViewChange = () => {},
  onMapClick,
}) {
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
    <MapContainer
      className="map"
      center={CITY_CENTER}
      zoom={13}
      minZoom={11}
      maxZoom={18}
      maxBounds={CITY_BOUNDS}
      maxBoundsViscosity={1.0}
      attributionControl={false}
    >
      {/* Leaflet's credit box, in the top right corner above the toolbar
          (map.css), so the sheet on phones never covers it. */}
      <AttributionControl position="topright" />
      <VectorBaseMap />

      {/* className must be a direct prop: react-leaflet applies pathOptions
          after the shape is created, and Leaflet ignores className then. */}
      <Polygon positions={[OUTER_RING, ...CITY_OUTLINE]} className="outside-mask" interactive={false} />

      {/* GeoJSON doesn't redraw when its data changes, so a new key forces
          a fresh layer. The key changes when a new result arrives, not when
          the dot moves, which happens before the result is back. */}
      {layer && <GridLayer cells={grid.cells} meta={grid.meta} {...layer} />}

      {stars.map(({ borough, spot }) => (
        <Marker key={borough} position={[spot.lat, spot.lng]} icon={STAR_ICON} keyboard={false}>
          <Tooltip direction="top" offset={[0, -16]} className="place-tooltip">
            Best spot for a new {CATEGORY_BY_ID[gapCategory].one}
            {spot.near ? `, near ${spot.near}` : ""}
          </Tooltip>
        </Marker>
      ))}

      {/* Your walk's layers. Hidden in the score map and gap finder, which cover the whole city. */}
      {walking && area && <GeoJSON key={areaKey} data={area} className="walk-area" interactive={false} />}
      {walking && <BarrierMarkers barriers={barriers} />}
      {walking && <PlaceMarkers places={places} />}

      {walking && selectedPoint && (
        <CircleMarker center={selectedPoint} radius={8} className="start-point" interactive={false} />
      )}
      {walking && selectedPoint && pending && (
        <Marker position={selectedPoint} icon={PENDING_ICON} interactive={false} keyboard={false} />
      )}
      {walking && <FitArea area={area} areaKey={area ? areaKey : null} />}

      {/* Why a click was turned away, at the spot itself (the panel says it too). */}
      {note && (
        <Popup
          key={note.key}
          position={note.point}
          className="map-note"
          autoPan={false}
          // Closing it (✕, or a click elsewhere) clears it, unless a newer one has replaced it.
          eventHandlers={{ remove: () => onNoteClose(note.key) }}
        >
          {note.text}
        </Popup>
      )}

      <FlyTo target={flyTo} />
      <FitTo target={fitTo} />
      <ViewWatcher onViewChange={onViewChange} />
      <ClickHandler onMapClick={onMapClick} />
    </MapContainer>
  );
}
