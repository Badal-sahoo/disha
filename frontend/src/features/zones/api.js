/**
 * F12 -- the road-cut editor. Fully implemented.
 */
import { api } from "@/shared/api/client";

/**
 * GET /api/zones
 * OUT: Promise<[{id, lat, lon, radius_km, severity, source, active, created_at}]>
 */
export function listZones() {
  return api.get("/zones").then((r) => r.data);
}

/**
 * POST /api/zones
 *
 * IN : zone = {lat: float, lon: float, radius_km: float, severity: int 1..5}
 *      severity 5 = impassable to anything without a hull.
 *      severity 1..4 = wheeled units are slowed, not stopped.
 * OUT: Promise<{id, lat, lon, radius_km, severity, source, active, created_at}>
 *
 * The server reweights the road graph, drops the Dijkstra cache, re-warms and
 * re-optimises -- measured at ~47 ms end to end. Ten seconds of demo,
 * disproportionate impact.
 */
export function createZone(zone) {
  return api.post("/zones", zone).then((r) => r.data);
}

/**
 * DELETE /api/zones/{id}
 *
 * IN : id = int
 * OUT: Promise<void>   -- 204, no body
 *
 * Water recedes. Same rebuild path in reverse.
 */
export function deleteZone(id) {
  return api.delete(`/zones/${id}`).then(() => undefined);
}
