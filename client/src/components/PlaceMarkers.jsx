import { CATEGORY_BY_ID } from "../data/categories";
import { nearestPlaces } from "../data/nearest";
import MapMarker from "./MapMarker";

// A marker per place: full or small, with or without a "?" badge for places
// whose opening hours aren't listed (card 10). The marker is HTML, so it
// reuses the same .glyph style as the panel.
function markerHtml(category, unknownHours) {
  const badge = unknownHours ? '<span class="hours-unknown">?</span>' : "";
  return `<span class="glyph">${category.glyph}</span>${badge}`;
}

export default function PlaceMarkers({ places }) {
  const nearest = nearestPlaces(places);
  return places.map((place) => {
    const key = `${place.category}:${place.id}`;
    const minor = !nearest.has(key);
    const category = CATEGORY_BY_ID[place.category];
    const unknown = place.status === "unknown";
    return (
      <MapMarker
        // One OpenStreetMap place can be in two categories (a grocery that is
        // also a pharmacy). With the id alone, React mixes up the two markers
        // and leaves one on the map after the walk moves.
        key={key}
        position={[place.lat, place.lng]}
        className={`place-marker cat-${category.id}${minor ? " place-marker--minor" : ""}`}
        html={markerHtml(category, unknown)}
        size={22}
        // The nearest ones sit on top of the small dots.
        onTop={!minor}
        tooltip={`${place.name ?? category.label}, ${formatMinutes(place.minutes)}${unknown ? ", hours unknown" : ""}`}
      />
    );
  });
}

export function formatMinutes(minutes) {
  const rounded = Math.max(1, Math.round(minutes));
  return `${rounded} min walk`;
}
