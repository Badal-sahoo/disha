/**
 * F14 -- supply allocation. Fully implemented.
 *
 * A transportation problem, not an assignment problem: different maths, same map.
 */
import { api } from "@/shared/api/client";

/**
 * GET /api/supply
 * OUT: Promise<[{id, depot, depot_code, item, quantity}]>
 *      item = "KIT" | "WATER" | "FOOD" | "MEDICAL"
 */
export function fetchStock() {
  return api.get("/supply").then((r) => r.data);
}

/**
 * GET /api/supply/plan
 *
 * IN : --
 * OUT: Promise<[{
 *        depot:    str,    // depot CODE, "DEP-02"
 *        shelter:  str,    // shelter CODE, "SHL-11"
 *        item:     str,    // "KIT" | "WATER" | "FOOD" | "MEDICAL"
 *        quantity: int,    // drives arrow width on the map
 *        cost:     float,  // km * quantity, the min-cost-flow objective term
 *      }]>
 *
 * Read-only preview. Nothing moves until commit.
 */
export function computeSupplyPlan() {
  return api.get("/supply/plan").then((r) => r.data);
}

/**
 * POST /api/supply/commit
 *
 * IN : flows = [{depot, shelter, item, quantity}, ...]
 * OUT: Promise<{committed: int,
 *               rejected: [{depot, shelter, item, reason}, ...]}>
 *      reason = "insufficient_stock" | "shelter_closed" | "unknown_code"
 *
 * Runs on a 15-minute batch, not on every report.
 */
export function commitSupplyPlan(flows) {
  return api.post("/supply/commit", { flows }).then((r) => r.data);
}
