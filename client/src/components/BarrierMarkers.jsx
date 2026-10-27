import { Marker, Tooltip } from "react-leaflet";
import L from "leaflet";
import { formatMinutes } from "./PlaceMarkers";

// Corners with no listed curb ramp, in wheelchair mode (card 11). A dark
// diamond with "!", so the shape alone tells them apart from the round
// place markers.
const ICON = L.divIcon({
  className: "barrier-marker",
  html: '<span class="barrier-marker__shape"><span>!</span></span>',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

export default function BarrierMarkers({ barriers }) {
  return barriers.map((b) => (
    <Marker
      key={`${b.lat},${b.lng}`}
      position={[b.lat, b.lng]}
      icon={ICON}
      // The panel says how many there are; each one isn't a Tab stop.
      keyboard={false}
    >
      <Tooltip direction="top" offset={[0, -10]} className="place-tooltip">
        No listed curb ramp, {formatMinutes(b.minutes)}
      </Tooltip>
    </Marker>
  ));
}
