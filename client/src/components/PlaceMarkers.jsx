import { Marker, Tooltip } from "react-leaflet";
import L from "leaflet";
import { CATEGORIES, CATEGORY_BY_ID } from "../data/categories";

// Two icons per category, made once: the usual one, and one with a "?"
// badge for places whose opening hours aren't listed (card 10). divIcon
// draws HTML, so the marker reuses the same .glyph style as the panel.
function makeIcon(category, unknownHours) {
  const badge = unknownHours ? '<span class="hours-unknown">?</span>' : "";
  return L.divIcon({
    className: `place-marker cat-${category.id}`,
    html: `<span class="glyph">${category.glyph}</span>${badge}`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

const ICONS = Object.fromEntries(CATEGORIES.map((c) => [c.id, makeIcon(c, false)]));
const UNKNOWN_ICONS = Object.fromEntries(CATEGORIES.map((c) => [c.id, makeIcon(c, true)]));

export default function PlaceMarkers({ places }) {
  return places.map((place) => (
    <Marker
      key={place.id}
      position={[place.lat, place.lng]}
      icon={(place.status === "unknown" ? UNKNOWN_ICONS : ICONS)[place.category]}
      // Hundreds of markers would each be a Tab stop. The panel lists the
      // same places for keyboard and screen reader users.
      keyboard={false}
    >
      <Tooltip direction="top" offset={[0, -12]} className="place-tooltip">
        {place.name ?? CATEGORY_BY_ID[place.category].label}, {formatMinutes(place.minutes)}
        {place.status === "unknown" && ", hours unknown"}
      </Tooltip>
    </Marker>
  ));
}

export function formatMinutes(minutes) {
  const rounded = Math.max(1, Math.round(minutes));
  return `${rounded} min walk`;
}
