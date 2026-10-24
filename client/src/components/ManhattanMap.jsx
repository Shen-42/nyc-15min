import {
  AttributionControl,
  CircleMarker,
  GeoJSON,
  MapContainer,
  Marker,
  Polygon,
  TileLayer,
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
export default function ManhattanMap({ selectedPoint, area, areaKey, places, onMapClick }) {
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
      {area && <GeoJSON key={areaKey} data={area} className="walk-area" interactive={false} />}

      <PlaceMarkers places={places} />

      {selectedPoint && (
        <CircleMarker center={selectedPoint} radius={8} className="start-point" interactive={false} />
      )}

      <ClickHandler onMapClick={onMapClick} />
    </MapContainer>
  );
}
