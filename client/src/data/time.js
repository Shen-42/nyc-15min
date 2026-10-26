// Time of day (card 10). Opening hours are New York hours, so "now" is the
// time in New York, wherever the visitor is.

const NYC_PARTS = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  hourCycle: "h23",
  weekday: "long",
});

// { date: "2026-10-26", hour: 13, weekday: "Monday" } for right now in New York.
export function nycNow() {
  const parts = Object.fromEntries(NYC_PARTS.formatToParts(new Date()).map((p) => [p.type, p.value]));
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    hour: Number(parts.hour),
    weekday: parts.weekday,
  };
}

// 0 -> "12 am", 13 -> "1 pm"
export function formatHour(hour) {
  const h = hour % 12 === 0 ? 12 : hour % 12;
  return `${h} ${hour < 12 ? "am" : "pm"}`;
}

// The form the server reads: "2026-10-26T21:00", today in New York.
export function atQuery(hour) {
  return `${nycNow().date}T${String(hour).padStart(2, "0")}:00`;
}
