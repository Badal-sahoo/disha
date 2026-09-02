/**
 * the full-snapshot endpoint. Fully implemented.
 */
import { api } from "@/shared/api/client";

/**
 * GET /api/state
 *
 * IN : bbox = {min_lon, min_lat, max_lon, max_lat} | null
 *      Pass null for the whole district. The server serialises it as
 *      "min_lon,min_lat,max_lon,max_lat" -- GeoJSON order, lon first.
 *
 * OUT: Promise<{
 *        t:           str,     // ISO 8601 server time
 *        incidents:   [{id, code, client_ref, lat, lon, kind, severity, people,
 *                       description, photo, source, reporter_phone, cell_id,
 *                       corroborations, status, reported_at, first_response_at}],
 *        resources:   [{id, code, name, kind, lat, lon, capabilities, capacity,
 *                       speed_kmph, status, free_at, base_name}],
 *        shelters:    [{id, code, name, lat, lon, capacity, occupancy,
 *                       remaining, status}],
 *        zones:       [{id, lat, lon, radius_km, severity, source, active,
 *                       created_at}],
 *        assignments: [{id, code, incident, incident_code, incident_lat,
 *                       incident_lon, resource, resource_code, resource_lat,
 *                       resource_lon, shelter, shelter_code, eta_min, gain,
 *                       status, leg, rescued_count, dispatched_at,
 *                       arrived_at, completed_at}],
 *        alerts:      [{id, identifier, event, severity, urgency, certainty,
 *                       polygon, sent_at, expires_at, active}],
 *        kpi:         {crit_mean, crit_p90, crit_sla_pct, unreached, awaiting},
 *      }>
 *
 * CALLED ON: page load, and after EVERY socket reconnect. Deltas missed while
 * disconnected are gone forever -- there is no replay buffer.
 */
export function fetchState(bbox = null) {
  const params = bbox
    ? { bbox: [bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat].join(",") }
    : {};
  return api.get("/state", { params }).then((r) => r.data);
}
