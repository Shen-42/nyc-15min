import MapMarker from "./MapMarker";
import { formatMinutes } from "./PlaceMarkers";

// Corners with no listed curb ramp, in wheelchair mode (card 11). A dark
// diamond with "!", so the shape alone tells them apart from the round
// place markers.
const HTML = '<span class="barrier-marker__shape"><span>!</span></span>';

export default function BarrierMarkers({ barriers }) {
  return barriers.map((b) => (
    <MapMarker
      key={`${b.lat},${b.lng}`}
      position={[b.lat, b.lng]}
      className="barrier-marker"
      html={HTML}
      size={18}
      tooltip={`No listed curb ramp, ${formatMinutes(b.minutes)}`}
      tooltipOffset={10}
    />
  ));
}
