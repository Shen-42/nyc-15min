import {
  MapContainer,
  TileLayer,
  Polygon,
  CircleMarker,
  Marker,
  GeoJSON,
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

export default function ManhattanMap({ selectedPoint, area, onMapClick }) {
  return (
    <MapContainer
      className="map"
      center={MANHATTAN_CENTER}
      zoom={13}
      minZoom={12}
      maxZoom={18}
      maxBounds={MANHATTAN_BOUNDS}
      maxBoundsViscosity={1.0}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {/* Gray mask over everything except Manhattan */}
      <Polygon
        positions={[OUTER_RING, ...MANHATTAN_POLYGONS]}
        pathOptions={{ color: "#666", weight: 1, fillColor: "#333", fillOpacity: 0.35 }}
        interactive={false}
      />

      {labelIcons.map((b) => (
        <Marker key={b.name} position={b.position} icon={b.icon} interactive={false} />
      ))}

      {/* The 15-minute walking area. GeoJSON doesn't redraw when its data
          changes, so a new key forces a fresh layer for each new area. */}
      {area && (
        <GeoJSON
          key={JSON.stringify(selectedPoint)}
          data={area}
          style={{ color: "#1f6feb", weight: 2, fillColor: "#1f6feb", fillOpacity: 0.2 }}
          interactive={false}
        />
      )}

      {selectedPoint && (
        <CircleMarker
          center={selectedPoint}
          radius={8}
          pathOptions={{ color: "#fff", weight: 2, fillColor: "#1f6feb", fillOpacity: 1 }}
        />
      )}

      <ClickHandler onMapClick={onMapClick} />
    </MapContainer>
  );
}
