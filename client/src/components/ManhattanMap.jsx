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
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <Polygon positions={[OUTER_RING, ...MANHATTAN_POLYGONS]} pathOptions={{ className: "outside-mask" }} interactive={false} />

      {labelIcons.map((b) => (
        <Marker key={b.name} position={b.position} icon={b.icon} interactive={false} keyboard={false} />
      ))}

      {/* GeoJSON doesn't redraw when its data changes, so a new key forces
          a fresh layer. The key changes when a new result arrives, not when
          the dot moves, which happens before the result is back. */}
      {area && <GeoJSON key={areaKey} data={area} className="walk-area" interactive={false} />}

      <PlaceMarkers places={places} />

      {selectedPoint && (
        <CircleMarker center={selectedPoint} radius={8} pathOptions={{ className: "start-point" }} interactive={false} />
      )}

      <ClickHandler onMapClick={onMapClick} />
    </MapContainer>
  );
}
