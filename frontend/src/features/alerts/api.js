/**
 * F13 -- the alert console. Fully implemented.
 */
import { api } from "@/shared/api/client";

/**
 * GET /api/alerts
 *
 * IN : active = bool (default true)
 *      bbox   = {min_lon, min_lat, max_lon, max_lat} | null
 * OUT: Promise<[{
 *        id:         int,
 *        identifier: str,     // the CAP identifier
 *        event:      str,     // "Cyclone Warning"
 *        severity:   str,     // "Minor"|"Moderate"|"Severe"|"Extreme"
 *        urgency:    str,     // "Immediate"|"Expected"|"Future"|"Past"
 *        certainty:  str,     // "Observed"|"Likely"|"Possible"|"Unlikely"
 *        polygon:    [[lat, lon], ...],   // LAT FIRST -- flip for GeoJSON
 *        sent_at:    str,     // ISO 8601
 *        expires_at: str|null,
 *        active:     bool,
 *      }]>   newest first
 */
export function fetchAlerts(active = true, bbox = null) {
  const params = { active };
  if (bbox) params.bbox = [bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat].join(",");
  return api.get("/alerts", { params }).then((r) => r.data);
}

/**
 * POST /api/alerts/{id}/preposition
 *
 * IN : id       = int
 *      maxUnits = int (default 5)
 * OUT: Promise<[assignment, ...]>   the staged dispatches
 *
 * The early-warning payoff, and demo beat two: units move toward the predicted
 * impact area before any citizen has reported anything.
 */
export function prePosition(id, maxUnits = 5) {
  return api.post(`/alerts/${id}/preposition`, { max_units: maxUnits }).then((r) => r.data);
}

/**
 * POST /api/alerts/{id}/broadcast
 *
 * IN : id       = int
 *      text     = str          <= 160 chars when SMS is one of the channels
 *      channels = ["PUSH"] | ["SMS"] | ["PUSH", "SMS"]
 * OUT: Promise<{queued: int, devices: int, numbers: int}>
 *
 * `queued`, not `sent` -- thousands of sends go to a task queue and must not
 * block the request.
 */
export function broadcastCitizenAlert(id, text, channels = ["PUSH"]) {
  return api.post(`/alerts/${id}/broadcast`, { text, channels }).then((r) => r.data);
}

/**
 * POST /api/devices  -- registers THIS browser for geofenced alerts.
 *
 * IN : token    = str, platform = str, lat = float, lon = float
 * OUT: Promise<{ok: true}>
 *
 * Here for completeness; the dashboard does not register itself. The mobile app
 * calls this. Round the location to ~1 km before sending -- you never need
 * street precision to warn someone a cyclone is coming.
 */
export function registerDevice(token, platform, lat, lon) {
  return api.post("/devices", { token, platform, lat, lon }).then((r) => r.data);
}
