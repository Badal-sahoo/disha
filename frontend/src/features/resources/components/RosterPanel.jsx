/**
 * the unit roster with the manual override. Fully wired.
 *
 * Filter by idle to see what is actually available right now.
 */
import { useState } from "react";

import {
  KIND_EMOJI,
  RESOURCE_KINDS,
  RESOURCE_STATUSES,
  STATUS_COLORS,
} from "@/shared/utils/constants";

import { useResources } from "../hooks";

export default function RosterPanel() {
  const [filter, setFilter] = useState({ status: "", kind: "" });
  const { resources, pending, error, setStatus } = useResources(filter);

  return (
    <div className="roster">
      <div className="roster__filters">
        <select
          value={filter.status}
          aria-label="Filter by status"
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
          aria-label="Filter by kind"
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
      {!resources.length && <p className="empty">No units match. Widen the filter.</p>}

      <ul className="roster__list">
        {resources.map((r) => (
          <li key={r.id}>
            <span className="dot" style={{ background: STATUS_COLORS[r.status] }} />
            {/* Same glyph the map pins use, so a unit is recognisable in both. */}
            <span className="roster__kind" aria-hidden="true">
              {KIND_EMOJI[r.kind] ?? KIND_EMOJI.TEAM}
            </span>
            <span className="roster__code">{r.code}</span>
            {/* ResourceSerializer has always sent `name` and `base_name`; the
                roster showed neither, so every unit read as a bare call sign. */}
            <span className="roster__name">{r.name || r.kind}</span>
            <select
              value={r.status}
              disabled={pending}
              aria-label={`Status of ${r.code}`}
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
