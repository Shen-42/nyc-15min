import { useEffect, useMemo } from "react";
import {
  AttributionControl,
  CircleMarker,
  GeoJSON,
  MapContainer,
  Marker,
  Polygon,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import { CITY_BOUNDS, CITY_CENTER, CITY_OUTLINE, OUTER_RING } from "../data/city";
import BarrierMarkers from "./BarrierMarkers";
import GridLayer from "./GridLayer";
import { CATEGORY_BY_ID } from "../data/categories";
import { cellScore, heatColor, hexToRgb, inPark, isGap } from "../data/grid";
import { smoothstep } from "../data/gridImage";
import PlaceMarkers from "./PlaceMarkers";

// Base map tiles. On the live site, Stadia allows requests by checking the
// site's domain (registered in the Stadia dashboard), so no key is needed.
// On localhost, requests without a key are heavily rate-limited, so a free
// key in client/.env.local (VITE_STADIA_API_KEY=...) is added when present.
// .env.local is not committed, so the key stays off GitHub.
const STADIA_KEY = import.meta.env.VITE_STADIA_API_KEY;
const TILE_URL =
  "https://tiles.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}{r}.png" +
  (STADIA_KEY ? `?api_key=${STADIA_KEY}` : "");

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
      {/* Stadia Maps "OSM Bright": green parks, blue water, colored roads.
          Free for non-commercial use (200,000 tiles a month). See TILE_URL. */}
      <TileLayer
        attribution='&copy; <a href="https://stadiamaps.com/attribution/" target="_blank">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/" target="_blank">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>'
        url={TILE_URL}
        maxZoom={18}
        // Only fetch tiles once a zoom finishes, not for every level passed
        // through on the way. Fewer requests, and fewer refused ones.
        updateWhenZooming={false}
        // Keep an extra ring of tiles around the view so short pans don't
        // show blank squares.
        keepBuffer={4}
      />

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

      <FlyTo target={flyTo} />
      <FitTo target={fitTo} />
      <ViewWatcher onViewChange={onViewChange} />
      <ClickHandler onMapClick={onMapClick} />
    </MapContainer>
  );
}
