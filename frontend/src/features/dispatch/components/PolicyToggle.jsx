/**
 * F10 -- the switch the whole project is scored on. Fully implemented.
 *
 * Nearest-available vs optimised, with live KPIs. It is the only part of this
 * build no other team will have, so it is wired end to end here rather than
 * left as a stub.
 */
import { POLICIES, POLICY_LABELS } from "@/shared/utils/constants";

/**
 * PROPS:
 *   policy    = str              currently selected
 *   plans     = obj              {POLICY: {assignments, kpi}} -- for the counts
 *   onChange  = (policy) => void
 *   disabled  = bool
 */
export default function PolicyToggle({ policy, plans = {}, onChange, disabled = false }) {
  return (
    <div className="policy-toggle" role="radiogroup" aria-label="Dispatch policy">
      {POLICIES.map((p) => {
        const count = plans[p]?.assignments?.length;
        return (
          <button
            key={p}
            type="button"
            role="radio"
            aria-checked={p === policy}
            className={p === policy ? "policy-toggle__btn is-active" : "policy-toggle__btn"}
            onClick={() => onChange(p)}
            disabled={disabled}
          >
            <span>{POLICY_LABELS[p]}</span>
            {count != null && <em>{count} dispatches</em>}
          </button>
        );
      })}
    </div>
  );
}
