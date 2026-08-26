/**
 * F12 -- click the map to mark a road flooded, and watch the fleet re-route.
 * Fully wired.
 *
 * PROPS: map = maplibregl.Map | null
 */
import { useState } from "react";

import { SEVERITY_COLORS } from "@/shared/utils/constants";

import { useZones } from "../hooks";

export default function ZoneEditor({ map }) {
  const { zones, drawing, pending, error, beginDraw, cancelDraw, remove } = useZones(map);
  const [severity, setSeverity] = useState(5);

  return (
    <div className="zone-editor">
      <div className="zone-editor__controls">
        <select value={severity} onChange={(e) => setSeverity(Number(e.target.value))}>
          {[1, 2, 3, 4, 5].map((s) => (
            <option key={s} value={s}>
              Severity {s}
              {s === 5 ? " - impassable" : ""}
            </option>
          ))}
        </select>

        {drawing ? (
          <button type="button" onClick={cancelDraw}>
            Cancel
          </button>
        ) : (
          <button type="button" onClick={() => beginDraw(severity)} disabled={!map || pending}>
            Mark road cut
          </button>
        )}
      </div>

      {error && <p className="error">{error.detail}</p>}

      <ul className="zone-editor__list">
        {zones.map((z) => (
          <li key={z.id}>
            <span className="dot" style={{ background: SEVERITY_COLORS[z.severity] }} />
            sev {z.severity} - {z.radius_km?.toFixed(1)} km
            <button type="button" onClick={() => remove(z.id)} disabled={pending}>
              Clear
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
