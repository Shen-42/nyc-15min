// Address search: NYC Planning Labs' GeoSearch, free and keyless, built on
// the city's own address database (PAD), so it knows every address in the
// five boroughs and nothing outside them.
// Docs: https://labs-geosearch-docs.netlify.app/docs
const GEOSEARCH_URL = "https://geosearch.planninglabs.nyc/v2";

// How many suggestions to show while typing.
export const MAX_SUGGESTIONS = 6;

// Suggestions for what's typed so far, as [{ label, lat, lng }].
// signal: an AbortSignal, so a newer keystroke can cancel an older request.
export async function findAddresses(text, { signal } = {}) {
  const res = await fetch(`${GEOSEARCH_URL}/autocomplete?text=${encodeURIComponent(text)}`, { signal });
  if (!res.ok) throw new Error(`Address search answered ${res.status}`);
  const data = await res.json();
  return (data.features ?? [])
    .filter((f) => f.geometry?.type === "Point" && f.properties?.label)
    .slice(0, MAX_SUGGESTIONS)
    .map((f) => ({
      label: tidyLabel(f.properties.label),
      lat: f.geometry.coordinates[1],
      lng: f.geometry.coordinates[0],
    }));
}

// GeoSearch spells streets in capitals and numbered streets without their
// ending ("350 WEST 42 STREET, Manhattan, New York, NY, USA"). Parts in all
// capitals become title case, numbered streets get "st", "nd", "rd", or
// "th" ("350 West 42nd Street"), state codes like NY stay, and ", USA" goes.
export function tidyLabel(label) {
  return label
    .replace(/, USA$/, "")
    .split(", ")
    .map((part) => (/[a-z]/.test(part) || /^[A-Z]{2}$/.test(part) ? part : addOrdinals(titleCase(part))))
    .join(", ");
}

// A number right before a street type that ends the street's name is a
// street's number, not a house number: "42 Street" -> "42nd Street", "149
// Place" -> "149th Place". Not in "3 Avenue U" or "1211 Avenue of the
// Americas", where the type is followed by more of the name.
const STREET_TYPES = "Street|Avenue|Road|Place|Drive|Terrace|Lane|Court|Way|Walk|Boulevard";
const NUMBERED_STREET = new RegExp(`\\b(\\d+) (${STREET_TYPES})$`);

function addOrdinals(text) {
  return text.replace(NUMBERED_STREET, (_, number, type) => `${number}${ordinal(Number(number))} ${type}`);
}

function ordinal(n) {
  if (n % 100 >= 11 && n % 100 <= 13) return "th"; // 11th, 112th
  return { 1: "st", 2: "nd", 3: "rd" }[n % 10] ?? "th";
}

function titleCase(text) {
  return text
    .toLowerCase()
    .replace(/(^|[\s\-/(])([a-z])/g, (_, before, letter) => before + letter.toUpperCase()) // each word: "Broadway"
    .replace(/\b(Mc|O')([a-z])/g, (_, prefix, letter) => prefix + letter.toUpperCase()) // "McGuinness", "O'Brien"
    .replace(/(?<= )(Of|The|And)(?= )/g, (word) => word.toLowerCase()); // "Avenue of the Americas"
}
