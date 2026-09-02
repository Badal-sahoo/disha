/**
 * click the map to mark a road flooded, and watch the fleet re-route.
 * Fully wired.
 *
 * PROPS: map = maplibregl.Map | null
 */
import { useState } from "react";

import { SEVERITY_COLORS } from "@/shared/utils/constants";

import { useZones } from "../hooks";

/* Folded on a phone, where it would otherwise cover the district. */
const opensByDefault = () => typeof window === "undefined" || window.innerWidth > 620;

export default function ZoneEditor({ map }) {
  const { zones, drawing, pending, error, beginDraw, cancelDraw, remove } = useZones(map);
  const [severity, setSeverity] = useState(5);

  return (
    <details className="map-instrument zone-editor" open={opensByDefault()}>
      <summary>Blocked roads</summary>

      <div className="map-instrument__body">
        <div className="zone-editor__controls">
          <select
            value={severity}
            onChange={(e) => setSeverity(Number(e.target.value))}
            aria-label="Severity of the block"
          >
            {[1, 2, 3, 4, 5].map((s) => (
              <option key={s} value={s}>
                Sev {s}
                {s === 5 ? " · impassable" : ""}
              </option>
            ))}
          </select>

          {drawing ? (
            <button type="button" onClick={cancelDraw}>
              Cancel
            </button>
          ) : (
            <button
              type="button"
              className="btn--commit"
              onClick={() => beginDraw(severity)}
              disabled={!map || pending}
            >
              Mark
            </button>
          )}
        </div>

        {drawing && <p className="label">Click the map to place it</p>}
        {error && <p className="error">{error.detail}</p>}

        {zones.length === 0 && !drawing && (
          <p className="empty">No roads marked. Every route is open.</p>
        )}

        <ul className="zone-editor__list">
          {zones.map((z) => (
            <li key={z.id}>
              <span className="dot" style={{ background: SEVERITY_COLORS[z.severity] }} />
              sev {z.severity} · {z.radius_km?.toFixed(1)} km
              <button
                type="button"
                className="btn--ghost"
                onClick={() => remove(z.id)}
                disabled={pending}
              >
                Clear
              </button>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}
