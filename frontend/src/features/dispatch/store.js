/**
 * Local state: the current dispatch plan.
 *
 * Separate from the live store on purpose -- a plan is a preview belonging to
 * one panel, while liveStore is the shared truth every feature reads.
 *
 * This used to hold three plans at once, one per policy, so an A/B toggle could
 * flip between them instantly. That was a comparison of algorithms, not a tool
 * for sending help, so it is gone: the panel solves one plan, the best one, and
 * the operator decides whether to send it.
 */
import { create } from "zustand";

export const useDispatchStore = create((set) => ({
  /** {assignments: [...]} | null -- proposals only; the KPI strip is
      measured-live and never reads from here. */
  plan: null,

  loading: false,
  error: null, // toApiError() shape

  setPlan: (plan) => set({ plan }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),

  /** After a commit the cached plan is stale. */
  clear: () => set({ plan: null, error: null }),
}));
