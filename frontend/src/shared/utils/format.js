/**
 * Display helpers. Implemented -- formatting is not logic, and every panel
 * needs the same "--" for missing values so an empty database looks deliberate
 * rather than broken.
 */

/** IN: minutes = float|null -- OUT: str  "12.4 min" | "--" */
export const minutes = (v) => (v == null || Number.isNaN(v) ? "--" : `${Number(v).toFixed(1)} min`);

/** IN: value = float|null, digits = int -- OUT: str */
export const num = (v, digits = 1) =>
  v == null || Number.isNaN(v) ? "--" : Number(v).toFixed(digits);

/** IN: value = float|null -- OUT: str  "87%" | "--" */
export const pct = (v) => (v == null || Number.isNaN(v) ? "--" : `${Math.round(Number(v))}%`);

/** IN: iso = str|null -- OUT: str  "14:32" | "--" */
export const clock = (iso) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "--";

/** IN: iso = str|null -- OUT: str  "26 Aug, 14:32" | "--" */
export const stamp = (iso) =>
  iso
    ? new Date(iso).toLocaleString([], {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "--";

/** IN: iso = str|null -- OUT: str  "12 min ago" | "--" */
export function ago(iso) {
  if (!iso) return "--";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  return `${Math.floor(mins / 60)} h ago`;
}
