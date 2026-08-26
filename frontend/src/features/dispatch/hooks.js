/**
 * F10 hooks. The fetch/flip plumbing is implemented; computeKpis -- the
 * client-side mirror of the server metric -- is the stub.
 *
 * Owner: Track 2 - Day 3
 */
import { useCallback, useEffect } from "react";

import { toApiError } from "@/shared/api/client";
import { useLiveStore } from "@/shared/store/liveStore";
import { POLICIES } from "@/shared/utils/constants";

import {
  commitAll as commitAllRequest,
  commitAssignments,
  explainAssignment,
  fetchPlan,
} from "./api";
import { useDispatchStore } from "./store";

/**
 * Fetch all three plans up front, then flip between them locally.
 *
 * IN : --
 * OUT: {
 *        policy:      str,
 *        plan:        {assignments, kpi} | null,
 *        plans:       obj,          // all three, keyed by policy
 *        loading:     bool,
 *        error:       obj|null,
 *        setPolicy:   (policy) => void,       // instant -- no round trip
 *        reload:      () => Promise<void>,
 *        commit:      (codes) => Promise<{committed, rejected}>,
 *        commitEvery: () => Promise<{committed, rejected}>,
 *      }
 *
 * Fetching all three at mount is what makes the toggle feel instant, and it is
 * also what makes the comparison fair: the three plans are computed from one
 * snapshot of the world, not three snapshots taken seconds apart.
 */
export function useDispatchPlan() {
  const { policy, plans, loading, error, setPolicy, setPlan, setLoading, setError, clear } =
    useDispatchStore();

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.all(POLICIES.map((p) => fetchPlan(p)));
      POLICIES.forEach((p, i) => setPlan(p, results[i]));
    } catch (e) {
      setError(toApiError(e));
    } finally {
      setLoading(false);
    }
  }, [setPlan, setLoading, setError]);

  useEffect(() => {
    reload();
  }, [reload]);

  const commit = useCallback(
    async (codes) => {
      const result = await commitAssignments(codes);
      clear(); // every cached plan is stale the moment one is committed
      await reload();
      return result;
    },
    [clear, reload]
  );

  const commitEvery = useCallback(async () => {
    const result = await commitAllRequest();
    clear();
    await reload();
    return result;
  }, [clear, reload]);

  return {
    policy,
    plan: plans[policy] ?? null,
    plans,
    loading,
    error,
    setPolicy,
    reload,
    commit,
    commitEvery,
  };
}

/**
 * Lazily fetch the explanation for one assignment.
 *
 * IN : --
 * OUT: {explain: (code) => Promise<{w, eta_min, gain, terms, alternatives}>}
 */
export function useExplain() {
  return { explain: useCallback((code) => explainAssignment(code), []) };
}

export function computeKpis(state, plan) {
  // F10 - Client-side mirror of the server metric, so the KPI strip moves the
  //       INSTANT the policy toggle flips instead of waiting for a round trip.
  //       The server value stays authoritative on the next tick.
  //
  // IN :
  //   state = the live store:
  //           {incidents: [{id, severity, status, reported_at,
  //                         first_response_at}], resources: [...], ...}
  //   plan  = [{id, code, incident, incident_code, resource_code, eta_min,
  //             gain, policy, status}]     // the PROPOSED assignments
  //
  // OUT: {
  //        crit_mean:    float,   // mean predicted minutes to first response,
  //                               //   over incidents with severity >= 4
  //        crit_p90:     float,   // 90th percentile of that list
  //        crit_sla_pct: float,   // 0..100, share of critical incidents whose
  //                               //   eta_min lands inside the SLA
  //        unreached:    int,     // OPEN severity >= 4 with no assignment in `plan`
  //        awaiting:     int,     // OPEN incidents with no assignment, any severity
  //      }
  //
  // HOW: for a PROPOSED plan there is no first_response_at yet, so predict it
  //      as assignment.eta_min. For already-DISPATCHED work use the real
  //      first_response_at where it exists. Match the server's arithmetic in
  //      dispatch/services.py compute_kpi() or the strip will visibly jump when
  //      the authoritative value arrives a second later.
  //
  // EDGE: return zeros, never NaN or null. An empty database must still render
  //       a KPI strip -- NaN reaches the DOM as "NaN" and looks broken on stage.
  throw new Error("TODO computeKpis -- Track 2 - Day 3");
}
