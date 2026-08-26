/**
 * F10 -- why this unit for this incident. Fully wired.
 *
 * The four priority terms must sum to w. Rendering them as proportional bars
 * makes a mismatch obvious at a glance, which is the point of an audit view.
 *
 * PROPS:
 *   code    = str|null      assignment code; null closes the drawer
 *   onClose = () => void
 */
import { useEffect, useState } from "react";

import { toApiError } from "@/shared/api/client";

import { explainAssignment } from "../api";

const TERM_LABELS = {
  severity: "Severity (0.45)",
  people: "People (0.25)",
  age: "Age (0.20)",
  corroboration: "Corroboration (0.10)",
};

export default function ExplainDrawer({ code, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!code) {
      setData(null);
      setError(null);
      return;
    }
    let cancelled = false;
    explainAssignment(code)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(toApiError(e)));
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (!code) return null;

  return (
    <aside className="explain-drawer">
      <header>
        <h3>{code}</h3>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </header>

      {error && <p className="error">{error.detail}</p>}

      {data && (
        <>
          <dl className="explain-drawer__summary">
            <dt>Priority (w)</dt>
            <dd>{data.w?.toFixed(3)}</dd>
            <dt>ETA</dt>
            <dd>{data.eta_min?.toFixed(1)} min</dd>
            <dt>Gain</dt>
            <dd>{data.gain?.toFixed(2)}</dd>
          </dl>

          <ul className="explain-drawer__terms">
            {Object.entries(data.terms ?? {}).map(([key, value]) => (
              <li key={key}>
                <span>{TERM_LABELS[key] ?? key}</span>
                <div className="bar">
                  <div className="bar__fill" style={{ width: `${(value / (data.w || 1)) * 100}%` }} />
                </div>
                <em>{value?.toFixed(3)}</em>
              </li>
            ))}
          </ul>

          {data.alternatives?.length > 0 && (
            <>
              <h4>Runners-up</h4>
              <ul className="explain-drawer__alts">
                {data.alternatives.map((alt) => (
                  <li key={alt.resource_code}>
                    {alt.resource_code} - {alt.eta_min?.toFixed(1)} min - {alt.reason}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </aside>
  );
}
