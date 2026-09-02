/**
 * resource and shelter management. Fully implemented.
 *
 * Let the operator correct reality. Units break down, shelters flood, and the
 * system must accept being told so.
 */
import { api, getList } from "@/shared/api/client";

/**
 * GET /api/resources
 *
 * IN : filter = {status?: str, kind?: str}
 *      status = "IDLE"|"ENROUTE"|"ONSCENE"|"TRANSPORTING"|"OUT_OF_SERVICE"
 *      kind   = "TEAM"|"BOAT"|"TRUCK"|"AMBULANCE"
 * OUT: Promise<[{id, code, name, kind, lat, lon, capabilities, capacity,
 *                speed_kmph, status, free_at, base_name}]>
 */
export function listResources(filter = {}) {
  return getList("/resources", { params: filter });
}

/**
 * PATCH /api/resources/{code}
 *
 * IN : code  = str   "BOAT-04"
 *      patch = {status?: str, lat?: float, lon?: float, capacity?: int}
 * OUT: Promise<resource>   the updated row
 *
 * A boat with a dead engine goes OUT_OF_SERVICE and leaves the next solve
 * immediately.
 */
export function updateResource(code, patch) {
  return api.patch(`/resources/${encodeURIComponent(code)}`, patch).then((r) => r.data);
}

/**
 * IN : code = str, status = str
 * OUT: Promise<resource>
 */
export function updateResourceStatus(code, status) {
  return updateResource(code, { status });
}

/**
 * GET /api/shelters
 *
 * IN : filter = {status?: "OPEN"|"FULL"|"INACCESSIBLE"}
 * OUT: Promise<[{id, code, name, lat, lon, capacity, occupancy, remaining,
 *                status}]>
 */
export function listShelters(filter = {}) {
  return getList("/shelters", { params: filter });
}

/**
 * GET /api/shelters/nearest
 *
 * IN : lat, lon = float, n = int (default 5), people = int (default 1)
 * OUT: Promise<[{...shelter, km: float, eta_min: float}]>
 *
 * Server-side ranking -- it knows live occupancy and which roads are cut. Never
 * compute this client-side from a stale list.
 */
export function nearestShelters(lat, lon, n = 5, people = 1) {
  return api.get("/shelters/nearest", { params: { lat, lon, n, people } }).then((r) => r.data);
}

/**
 * PATCH /api/shelters/{code}
 *
 * IN : code  = str
 *      patch = {status?: str, occupancy_delta?: int}
 *      occupancy_delta is SIGNED and relative -- +12 when a walk-in group
 *      arrives, -12 when they leave. Never send an absolute occupancy, or two
 *      concurrent edits overwrite each other.
 * OUT: Promise<shelter>
 */
export function updateShelter(code, patch) {
  return api.patch(`/shelters/${encodeURIComponent(code)}`, patch).then((r) => r.data);
}

/** IN: code = str, status = str -- OUT: Promise<shelter> */
export function setShelterStatus(code, status) {
  return updateShelter(code, { status });
}

/** IN: code = str, delta = int (signed) -- OUT: Promise<shelter> */
export function adjustOccupancy(code, delta) {
  return updateShelter(code, { occupancy_delta: delta });
}
