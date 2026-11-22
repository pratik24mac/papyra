// Same token format as the engine (backend/docmaster/docgen/dates.py), so the review step can show
// a date exactly as it will print. D DD Do · M MM MMM MMMM · YY YYYY · ddd dddd.
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const TOKEN = /dddd|ddd|DD|Do|D|MMMM|MMM|MM|M|YYYY|YY/g;

export const DEFAULT_DATE_FORMAT = "D MMMM YYYY";

function ordinal(n: number): string {
  const r = n % 100;
  return `${n}${r >= 11 && r <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
}

/** Format an ISO date (YYYY-MM-DD) with the token format; anything else is returned unchanged. */
export function formatDate(iso: unknown, fmt: string = DEFAULT_DATE_FORMAT): string {
  if (typeof iso !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return String(iso ?? "");
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  if (Number.isNaN(date.getTime())) return iso;
  if (fmt.includes("%")) return iso;                       // strftime formats are the engine's business
  const rep: Record<string, string> = { D: String(d), DD: String(d).padStart(2, "0"), Do: ordinal(d), M: String(m), MM: String(m).padStart(2, "0"),
    MMM: MONTHS[m - 1].slice(0, 3), MMMM: MONTHS[m - 1], YY: String(y % 100).padStart(2, "0"), YYYY: String(y), ddd: DAYS[date.getUTCDay()].slice(0, 3), dddd: DAYS[date.getUTCDay()] };
  return fmt.replace(TOKEN, (t) => rep[t]);
}

/** Effective format for a field: field `format` → the user's Settings choice → template default → built-in. */
export function effectiveDateFormat(fieldFormat: string | undefined, appFormat: string | null | undefined, templateFormat: string | undefined): string {
  return fieldFormat || appFormat || templateFormat || DEFAULT_DATE_FORMAT;
}
