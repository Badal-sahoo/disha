/**
 * Endpoints the OPS DASHBOARD never calls -- the citizen and responder halves
 * of the API (F1-F6).
 *
 * They are written and kept in step here so the React Native team copies ONE
 * file into ../app rather than re-deriving twenty request shapes from the spec.
 * Nothing in the dashboard imports this module, and that is intentional.
 *
 * Fully implemented.
 */
import { api } from "./client";

// ---------------------------------------------------------------------------
// F1 -- citizen: report an incident
// ---------------------------------------------------------------------------

/**
 * POST /api/reports
 *
 * IN : draft = {
 *        client_ref:     str,       // UUID the PHONE generates. The dedupe key --
 *                                   //   posting twice gives one row, which is
 *                                   //   what makes the offline queue safe.
 *        lat:            float,
 *        lon:            float,
 *        kind:           str,       // "FLOOD" | "CYCLONE" | "LANDSLIDE"
 *        severity:       int,       // 1..5
 *        people:         int,
 *        description:    str,
 *        photo:          File|null, // <= 500 KB. Optional -- NEVER gate
 *                                   //   submission on it.
 *        accuracy_m:     float,     // GPS accuracy; used for triage, not stored
 *        reporter_phone: str,
 *      }
 * OUT: Promise<{id, code, status, cell_id, corroborations, ...incident}>
 *
 * Sends multipart when a photo is attached, JSON otherwise.
 */
export function submitReport(draft) {
  if (!draft.photo) return api.post("/reports", draft).then((r) => r.data);

  const form = new FormData();
  Object.entries(draft).forEach(([k, v]) => v != null && form.append(k, v));
  return api
    .post("/reports", form, { headers: { "Content-Type": "multipart/form-data" } })
    .then((r) => r.data);
}

/**
 * GET /api/reports/{code}
 * IN : code = str  -- OUT: Promise<incident + {assignments: [...]}>
 */
export function fetchReport(code) {
  return api.get(`/reports/${encodeURIComponent(code)}`).then((r) => r.data);
}

// ---------------------------------------------------------------------------
// F4 -- citizen: find shelter
// ---------------------------------------------------------------------------

/**
 * GET /api/shelters/nearest
 * IN : lat, lon = float, n = int, people = int
 * OUT: Promise<[{...shelter, km, eta_min}]>
 */
export function nearestShelters(lat, lon, n = 5, people = 1) {
  return api.get("/shelters/nearest", { params: { lat, lon, n, people } }).then((r) => r.data);
}

// ---------------------------------------------------------------------------
// F5 -- responder: my assignment
// ---------------------------------------------------------------------------

/**
 * GET /api/responder/assignment
 *
 * IN : -- (the unit comes off the JWT, not the URL)
 * OUT: Promise<assignment | null>
 *
 * Cold start and reconnect path. The socket is the fast path; this is the truth.
 */
export function fetchMyAssignment() {
  return api.get("/responder/assignment").then((r) => r.data);
}

/**
 * POST /api/responder/assignment/{code}/status
 *
 * IN : code   = str
 *      status = "ACCEPTED"|"EN_ROUTE"|"ON_SCENE"|"TRANSPORTING"|"COMPLETE"
 *      note   = str
 * OUT: Promise<{ok: true, next: str|null}>
 *
 * Until a team ACCEPTS, the optimiser may still reassign the job. After accept,
 * it is frozen.
 */
export function updateAssignmentStatus(code, status, note = "") {
  return api
    .post(`/responder/assignment/${encodeURIComponent(code)}/status`, { status, note })
    .then((r) => r.data);
}

/**
 * POST /api/responder/assignment/{code}/headcount
 *
 * IN : code = str, rescued = int, note = str
 * OUT: Promise<{ok: true, incident_status: str}>
 *
 * Ground truth versus the citizen's estimate. Closes the incident.
 */
export function reportHeadcount(code, rescued, note = "") {
  return api
    .post(`/responder/assignment/${encodeURIComponent(code)}/headcount`, { rescued, note })
    .then((r) => r.data);
}

/**
 * POST /api/responder/location  -- the beacon, every 20 s.
 * IN : lat, lon = float, ts = ISO 8601 | undefined
 * OUT: Promise<{ok: true}>
 */
export function pushLocation(lat, lon, ts) {
  return api.post("/responder/location", { lat, lon, ts }).then((r) => r.data);
}

// ---------------------------------------------------------------------------
// F6 -- responder: flood-aware navigation
// ---------------------------------------------------------------------------

/**
 * GET /api/route
 *
 * IN : from   = {lat, lon}
 *      to     = {lat, lon}
 *      vclass = "TRUCK" | "BOAT" | "TEAM" | "AMBULANCE"
 * OUT: Promise<{polyline: [[lat, lon], ...], minutes: float}>
 *
 * From your own road graph, which knows which edges are cut. Google does not
 * know the causeway washed out an hour ago -- this is the one place you must
 * not hand off.
 */
export function fetchRoute(from, to, vclass = "TRUCK") {
  return api
    .get("/route", {
      params: { from: `${from.lat},${from.lon}`, to: `${to.lat},${to.lon}`, vclass },
    })
    .then((r) => r.data);
}

// ---------------------------------------------------------------------------
// Machine callers -- the SMS gateway and the IVR simulator.
// Both need the X-Gateway-Secret header; they are NOT browser endpoints.
// ---------------------------------------------------------------------------

/**
 * POST /api/sms
 * IN : {from, body, received_at, gateway_id}, secret = str
 * OUT: Promise<{code, parsed, confidence, incident_id}>
 */
export function postSms(payload, secret) {
  return api.post("/sms", payload, { headers: { "X-Gateway-Secret": secret } }).then((r) => r.data);
}

/**
 * POST /api/ivr
 * IN : {session_id, digit, from}, secret = str
 * OUT: Promise<{prompt, done, code, incident_id, state}>
 */
export function postIvr(payload, secret) {
  return api.post("/ivr", payload, { headers: { "X-Gateway-Secret": secret } }).then((r) => r.data);
}
