/**
 * F11 -- the unit roster with the manual override. Fully wired.
 *
 * Filter by idle to see what is actually available right now.
 */
import { useState } from "react";

import { RESOURCE_KINDS, RESOURCE_STATUSES, STATUS_COLORS } from "@/shared/utils/constants";

import { useResources } from "../hooks";

export default function RosterPanel() {
  const [filter, setFilter] = useState({ status: "", kind: "" });
  const { resources, pending, error, setStatus } = useResources(filter);

  return (
    <div className="roster">
      <div className="roster__filters">
        <select
          value={filter.status}
          onChange={(e) => setFilter((f) => ({ ...f, status: e.target.value }))}
        >
          <option value="">All statuses</option>
          {RESOURCE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={filter.kind}
          onChange={(e) => setFilter((f) => ({ ...f, kind: e.target.value }))}
        >
          <option value="">All kinds</option>
          {RESOURCE_KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="error">{error.detail}</p>}
      {!resources.length && <p className="muted">No units match.</p>}

      <ul className="roster__list">
        {resources.map((r) => (
          <li key={r.id}>
            <span className="dot" style={{ background: STATUS_COLORS[r.status] }} />
            <span className="roster__code">{r.code}</span>
            <span className="muted">{r.kind}</span>
            <select
              value={r.status}
              disabled={pending}
              onChange={(e) => setStatus(r.code, e.target.value)}
            >
              {RESOURCE_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </li>
        ))}
      </ul>
    </div>
  );
}
