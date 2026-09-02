/**
 * the dispatch endpoints. Fully implemented.
 *
 * plan and commit are deliberately separate calls. That separation is what lets
 * the operator refresh the preview as often as they like without dispatching
 * a single boat by accident.
 */
import { api } from "@/shared/api/client";

/**
 * GET /api/dispatch/plan
 *
 * OUT: Promise<{
 *        assignments: [{id, code, incident, incident_code, incident_lat,
 *                       incident_lon, resource, resource_code, resource_lat,
 *                       resource_lon, shelter, shelter_code, eta_min, gain,
 *                       status, leg, dispatched_at}],   // status "PROPOSED"
 *      }>
 *
 * A PREVIEW -- nothing is written and no unit is told anything. The server
 * computes all three policies from the SAME state, which is what makes the
 * comparison honest rather than a claim.
 */
export function fetchPlan() {
  return api.get("/dispatch/plan").then((r) => r.data);
}

/**
 * POST /api/dispatch/commit
 *
 * IN : codes = [str, ...]   e.g. ["ASG0088"]  -- commit these
 * OUT: Promise<{committed: int, rejected: [{code: str, reason: str}, ...]}>
 *      reason is "unit_taken" | "shelter_full" | "incident_closed"
 *
 * A non-empty rejected[] is normal, not an error: the world moved while the
 * operator was deciding. Show it, do not swallow it.
 */
export function commitAssignments(codes) {
  return api.post("/dispatch/commit", { codes }).then((r) => r.data);
}

/**
 * POST /api/dispatch/commit  with {all: true}
 *
 * IN : --
 * OUT: Promise<{committed: int, rejected: [...]}>
 *
 * Auto-dispatch. Have it, demo it, but keep the UI open on manual --
 * "the human is in the loop" is the right answer to the governance question.
 */
export function commitAll() {
  return api.post("/dispatch/commit", { all: true }).then((r) => r.data);
}

/**
 * GET /api/dispatch/{code}/explain
 *
 * IN : code   = str   "ASG0088"
 *                     than ASG0003 under OPTIMIZED -- send the wrong one and
 *                     the server explains the wrong dispatch.
 * OUT: Promise<{
 *        w:       float,      // total priority, 0..1
 *        eta_min: float,
 *        gain:    float,      // w * (120 - eta_min)
 *        terms: {
 *          severity:      float,   // 0.45 weight
 *          people:        float,   // 0.25
 *          age:           float,   // 0.20
 *          corroboration: float,   // 0.10
 *        },                        // the four MUST sum to w
 *        alternatives: [{resource_code: str, eta_min: float, gain: float,
 *                        reason: str}],
 *      }>
 *
 * The audit view, and the answer to "why should NDRF trust this?"
 */
export function explainAssignment(code) {
  return api
    .get(`/dispatch/${encodeURIComponent(code)}/explain`)
    .then((r) => r.data);
}

/**
 * GET /api/kpi
 *
 * OUT: Promise<{crit_mean, crit_p90, crit_sla_pct, unreached, awaiting}>
 */
export function fetchKpi() {
  return api.get("/kpi").then((r) => r.data);
}
