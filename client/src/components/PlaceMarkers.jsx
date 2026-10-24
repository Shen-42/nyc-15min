import { Marker, Tooltip } from "react-leaflet";
import L from "leaflet";
import { CATEGORIES, CATEGORY_BY_ID } from "../data/categories";

// One icon per category, made once. divIcon draws HTML, so the marker
// reuses the same .glyph style as the panel.
const ICONS = Object.fromEntries(
  CATEGORIES.map((c) => [
    c.id,
    L.divIcon({
      className: `place-marker cat-${c.id}`,
      html: `<span class="glyph">${c.glyph}</span>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    }),
  ])
);

export default function PlaceMarkers({ places }) {
  return places.map((place) => (
    <Marker
      key={place.id}
      position={[place.lat, place.lng]}
      icon={ICONS[place.category]}
      // Hundreds of markers would each be a Tab stop. The panel lists the
      // same places for keyboard and screen reader users.
      keyboard={false}
    >
      <Tooltip direction="top" offset={[0, -12]} className="place-tooltip">
        {place.name ?? CATEGORY_BY_ID[place.category].label}, {formatMinutes(place.minutes)}
      </Tooltip>
    </Marker>
  ));
}

export function formatMinutes(minutes) {
  const rounded = Math.max(1, Math.round(minutes));
  return `${rounded} min walk`;
}
