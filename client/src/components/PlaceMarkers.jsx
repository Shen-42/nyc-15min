import { Marker, Tooltip } from "react-leaflet";
import L from "leaflet";
import { CATEGORIES, CATEGORY_BY_ID } from "../data/categories";
import { nearestPlaces } from "../data/nearest";

// Icons per category, made once: full or small, with or without a "?"
// badge for places whose opening hours aren't listed (card 10). divIcon
// draws HTML, so the marker reuses the same .glyph style as the panel.
function makeIcon(category, unknownHours, minor) {
  const badge = unknownHours ? '<span class="hours-unknown">?</span>' : "";
  return L.divIcon({
    className: `place-marker cat-${category.id}${minor ? " place-marker--minor" : ""}`,
    html: `<span class="glyph">${category.glyph}</span>${badge}`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

const iconSet = (unknownHours, minor) => Object.fromEntries(CATEGORIES.map((c) => [c.id, makeIcon(c, unknownHours, minor)]));
const ICONS = {
  full: { known: iconSet(false, false), unknown: iconSet(true, false) },
  minor: { known: iconSet(false, true), unknown: iconSet(true, true) },
};

export default function PlaceMarkers({ places }) {
  const nearest = nearestPlaces(places);
  return places.map((place) => {
    const key = `${place.category}:${place.id}`;
    const size = nearest.has(key) ? "full" : "minor";
    return (
    <Marker
      // One OpenStreetMap place can be in two categories (a grocery that is
      // also a pharmacy). With the id alone, React mixes up the two markers
      // and leaves one on the map after the walk moves.
      key={key}
      position={[place.lat, place.lng]}
      icon={ICONS[size][place.status === "unknown" ? "unknown" : "known"][place.category]}
      // The nearest ones sit on top of the small dots.
      zIndexOffset={size === "full" ? 1000 : 0}
      // Hundreds of markers would each be a Tab stop. The panel lists the
      // same places for keyboard and screen reader users.
      keyboard={false}
    >
      <Tooltip direction="top" offset={[0, -12]} className="place-tooltip">
        {place.name ?? CATEGORY_BY_ID[place.category].label}, {formatMinutes(place.minutes)}
        {place.status === "unknown" && ", hours unknown"}
      </Tooltip>
    </Marker>
    );
  });
}

export function formatMinutes(minutes) {
  const rounded = Math.max(1, Math.round(minutes));
  return `${rounded} min walk`;
}
