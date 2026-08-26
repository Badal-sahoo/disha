/**
 * F15 -- timeline and after-action. Fully implemented.
 */
import { api, API_URL } from "@/shared/api/client";

/**
 * GET /api/timeline
 *
 * IN : from, to = ISO 8601 strings
 * OUT: Promise<[{
 *        t:    str,   // ISO 8601
 *        type: str,   // the SAME ten strings as the WebSocket events
 *        data: obj,   // the payload that was broadcast at the time
 *      }]>   ascending by t
 *
 * The event log IS the timeline -- do not build a second store for it.
 */
export function fetchTimeline(from, to) {
  return api.get("/timeline", { params: { from, to } }).then((r) => r.data);
}

/**
 * GET /api/after-action
 *
 * IN : from, to = ISO 8601, format = "csv" | "pdf"
 * OUT: Promise<Blob>
 *
 * Response times by severity, unserved incidents, shelter utilisation, and
 * every dispatch with its gain -- the gain column is what makes it auditable
 * rather than a summary.
 *
 * responseType "blob" is required, or axios parses the bytes as text and the
 * PDF arrives corrupted.
 */
export function exportAfterAction(from, to, format = "csv") {
  return api
    .get("/after-action", { params: { from, to, format }, responseType: "blob" })
    .then((r) => r.data);
}

/**
 * Trigger a browser download of the report.
 *
 * IN : blob     = Blob
 *      filename = str
 * OUT: void
 */
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export { API_URL };
