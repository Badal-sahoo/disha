/**
 * Fetches the dispatch plan and commits it.
 */
import { useCallback, useEffect } from "react";

import { toApiError } from "@/shared/api/client";
import { useLiveStore } from "@/shared/store/liveStore";

import {
  commitAll as commitAllRequest,
  commitAssignments,
  explainAssignment,
  fetchPlan,
} from "./api";
import { useDispatchStore } from "./store";

/**
 * The current dispatch plan: who should go where, right now.
 *
 * IN : --
 * OUT: {
 *        plan:        {assignments} | null,
 *        loading:     bool,
 *        error:       obj|null,
 *        reload:      () => Promise<void>,
 *        commit:      (codes) => Promise<{committed, rejected}>,
 *        commitEvery: () => Promise<{committed, rejected}>,
 *      }
 *
 * One solve, not three. This used to fetch a plan per policy so the panel could
 * A/B them live; that compared algorithms rather than getting anyone out of the
 * water, and it made every reload three solves deep.
 */
export function useDispatchPlan() {
  const { plan, loading, error, setPlan, setLoading, setError, clear } =
    useDispatchStore();

  // A primitive, so zustand re-renders only when the count actually moves.
  const planInputKey = useLiveStore(
    (s) =>
      `${s.incidents.filter((i) => i.status === "OPEN").length}:` +
      `${s.resources.filter((r) => r.status === "IDLE").length}`
  );

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPlan(await fetchPlan());
    } catch (e) {
      setError(toApiError(e));
    } finally {
      setLoading(false);
    }
  }, [setPlan, setLoading, setError]);

  // Re-solve whenever the solver's INPUT changes -- a new report arriving, or a
  // unit coming free. Fetching once on mount left the panel showing a plan for
  // a district that had moved on, which reads as "dispatch is not running".
  //
  // Keyed on the open/idle counts rather than on the store's `t`, which also
  // ticks for kpi and shelter deltas that cannot change the plan.
  useEffect(() => {
    reload();
  }, [reload, planInputKey]);

  // Drop the plan when the panel goes away.
  //
  // The KPI strip lives in the shell and is mounted for the whole session, so a
  // plan left in the store kept it tinted and labelled "Forecast" on the Live
  // map -- predicting the effect of a plan the operator had navigated away from
  // and could no longer see. The forecast belongs to the Dispatch screen.
  useEffect(() => clear, [clear]);

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
    plan,
    loading,
    error,
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
