/**
 * F11 -- shelter status and walk-in occupancy. Fully wired.
 *
 * Occupancy must be editable or it drifts from reality within the hour.
 */
import { SHELTER_STATUSES } from "@/shared/utils/constants";

import { useShelters } from "../hooks";

export default function ShelterPanel() {
  const { shelters, pending, error, setStatus, adjust } = useShelters();

  return (
    <div className="shelter-panel">
      {error && <p className="error">{error.detail}</p>}
      {!shelters.length && <p className="muted">No shelters loaded.</p>}

      <ul className="shelter-panel__list">
        {shelters.map((s) => (
          <li key={s.id}>
            <span className="shelter-panel__code">{s.code}</span>
            <span className="muted">
              {s.occupancy} / {s.capacity}
            </span>
            <div className="shelter-panel__walkins">
              <button type="button" disabled={pending} onClick={() => adjust(s.code, -10)}>
                -10
              </button>
              <button type="button" disabled={pending} onClick={() => adjust(s.code, 10)}>
                +10
              </button>
            </div>
            <select
              value={s.status}
              disabled={pending}
              onChange={(e) => setStatus(s.code, e.target.value)}
            >
              {SHELTER_STATUSES.map((st) => (
                <option key={st} value={st}>
                  {st}
                </option>
              ))}
            </select>
          </li>
        ))}
      </ul>
    </div>
  );
}
