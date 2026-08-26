/**
 * F10 local state: the three fetched plans and which one is showing.
 *
 * Fully implemented. Separate from the live store on purpose -- plans are a
 * preview that belongs to one panel, while liveStore is the shared truth every
 * feature reads.
 */
import { create } from "zustand";

export const useDispatchStore = create((set, get) => ({
  /** "OPTIMIZED" | "GREEDY" | "GREEDY_SEVERITY" -- opens on the optimiser */
  policy: "OPTIMIZED",

  /**
   * All three plans, keyed by policy, so flipping the toggle is instant rather
   * than a round trip:
   *   {OPTIMIZED: {assignments, kpi}, GREEDY: {...}, GREEDY_SEVERITY: {...}}
   */
  plans: {},

  loading: false,
  error: null, // toApiError() shape

  /** IN: policy = str -- OUT: void */
  setPolicy: (policy) => set({ policy }),

  /**
   * IN : policy = str
   *      plan   = {assignments: [...], kpi: {...}}
   * OUT: void
   */
  setPlan: (policy, plan) => set((s) => ({ plans: { ...s.plans, [policy]: plan } })),

  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),

  /** Drop every cached plan -- after a commit, they are all stale. */
  clear: () => set({ plans: {}, error: null }),

  /** OUT: {assignments, kpi} | null -- the plan for the selected policy */
  currentPlan: () => get().plans[get().policy] ?? null,
}));
