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
import {
  MANHATTAN_CENTER,
  MANHATTAN_BOUNDS,
  MANHATTAN_POLYGONS,
  OUTER_RING,
  COMING_SOON_LABELS,
} from "../data/manhattan";
import BarrierMarkers from "./BarrierMarkers";
import GridLayer from "./GridLayer";
import { CATEGORY_BY_ID } from "../data/categories";
import { cellScore, heatColor, hexToRgb, inPark, isGap } from "../data/grid";
import { smoothstep } from "../data/gridImage";
import PlaceMarkers from "./PlaceMarkers";

// Text labels for the other boroughs. divIcon draws HTML instead of an image.
const labelIcons = COMING_SOON_LABELS.map((b) => ({
  ...b,
  icon: L.divIcon({
    className: "borough-label",
    html: `${b.name}<br/><span>coming soon</span>`,
    iconSize: [120, 36],
    iconAnchor: [60, 18],
  }),
}));

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
export default function ManhattanMap({
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
  onMapClick,
}) {
  // What the score map or gap finder draws (card 12): a value for each grid
  // cell, and a color for each value. data/gridImage.js smooths the values
  // into a gradient. Park cells have no value, since nobody lives there.
  const layer = useMemo(() => {
    if (!grid || view === "walk") return null;
    const categories = grid.meta.categories;
    if (view === "heat") {
      // Parks have no value of their own (nobody lives there), and are
      // filled in from the blocks around them so the gradient has no holes.
      return {
        valueFor: (cell) => (inPark(cell) ? null : cellScore(cell, categories, weights)),
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
      valueFor: (cell) => (inPark(cell) ? null : isGap(cell, categories, gapCategory) ? 1 : 0),
      colorFor: (share) => (share < 0.1 ? null : [...rgb, 0.9 * smoothstep(0.1, 0.45, share)]),
      sigma: 0.9,
      blank: [...grid.parks, ...grid.water],
    };
  }, [grid, view, weights, gapCategory]);

  const walking = view === "walk";
  const best = view === "gaps" && grid ? grid.gaps[gapCategory].best : null;

  return (
    <MapContainer
      className="map"
      center={MANHATTAN_CENTER}
      zoom={13}
      minZoom={12}
      maxZoom={18}
      maxBounds={MANHATTAN_BOUNDS}
      maxBoundsViscosity={1.0}
      attributionControl={false}
    >
      {/* Top right, so the results sheet on phones doesn't cover the credit. */}
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
      <Polygon positions={[OUTER_RING, ...MANHATTAN_POLYGONS]} className="outside-mask" interactive={false} />

      {labelIcons.map((b) => (
        <Marker key={b.name} position={b.position} icon={b.icon} interactive={false} keyboard={false} />
      ))}

      {/* GeoJSON doesn't redraw when its data changes, so a new key forces
          a fresh layer. The key changes when a new result arrives, not when
          the dot moves, which happens before the result is back. */}
      {layer && <GridLayer cells={grid.cells} cellM={grid.meta.cell_m} {...layer} />}

      {best && (
        <Marker position={[best.lat, best.lng]} icon={STAR_ICON} keyboard={false}>
          <Tooltip direction="top" offset={[0, -16]} className="place-tooltip">
            Best spot for a new {CATEGORY_BY_ID[gapCategory].one}
            {best.near ? `, near ${best.near}` : ""}
          </Tooltip>
        </Marker>
      )}

      {/* Your walk's layers. Hidden in the score map and gap finder, which cover all of Manhattan. */}
      {walking && area && <GeoJSON key={areaKey} data={area} className="walk-area" interactive={false} />}
      {walking && <BarrierMarkers barriers={barriers} />}
      {walking && <PlaceMarkers places={places} />}

      {walking && selectedPoint && (
        <CircleMarker center={selectedPoint} radius={8} className="start-point" interactive={false} />
      )}

      <FlyTo target={flyTo} />
      <ClickHandler onMapClick={onMapClick} />
    </MapContainer>
  );
}
