/**
 * One box that says what is drawn on the map, and lets the operator turn any of
 * it off.
 *
 * A lone "Heatmap" checkbox told you nothing about the other seven things on
 * screen. This lists all of them, so the purple lines and the red circles stop
 * being a mystery.
 *
 * It also carries a swatch per row in the colour that layer actually paints
 * with, which makes this list double as the map's legend -- previously there
 * was none, and the two colour ladders had to be learned by trial.
 *
 * PROPS: map = maplibregl.Map | null
 */
import { useEffect, useState } from "react";

import {
  SEVERITY_COLORS,
  SHELTER_COLORS,
  STATUS_COLORS,
} from "@/shared/utils/constants";

/**
 * What the operator sees, and which MapLibre layers it controls. Most entries
 * drive two layers, because a shape needs both a fill and an outline, and a
 * route needs its casing turned off with it.
 */
const LAYER_GROUPS = [
  { key: "incidents", label: "Incidents", hint: "one circle per village; zoom in for each family",
    swatch: SEVERITY_COLORS[4],
    layers: ["incidents-point", "incidents-halo", "incidents-critical",
             "incidents-scene", "incidents-scene-halo"] },
  { key: "risk", label: "Flood risk", hint: "red shore → green inland",
    swatch: SEVERITY_COLORS[5], layers: ["risk-heat", "risk-sea-mask"] },
  { key: "units", label: "Rescue units", hint: "hollow ring; colour is status",
    swatch: STATUS_COLORS.IDLE, layers: ["resources-point", "resources-casing"] },
  { key: "routes", label: "Dispatch routes", hint: "unit to incident",
    swatch: STATUS_COLORS.ENROUTE, layers: ["assignments-line", "assignments-casing"] },
  { key: "shelters", label: "Shelters & hospitals", hint: "ringed disc; colour is room left",
    swatch: SHELTER_COLORS.OPEN, layers: ["shelters-point"] },
  { key: "zones", label: "Blocked zones", hint: "cut or flooded roads",
    swatch: SEVERITY_COLORS[5], layers: ["zones-fill", "zones-line"] },
];

// Flood risk starts OFF. It is planning context, not live state: an operator
// opens the map to see what is happening now, and a full-width colour wash is
// the wrong thing to meet them with. It is one click away when it is wanted.
const INITIALLY_HIDDEN = ["risk"];

/* On a phone these instruments cover the district they are describing, so they
   start folded. <details> does the folding natively -- no state, no script. */
const opensByDefault = () => typeof window === "undefined" || window.innerWidth > 620;

export default function MapLayers({ map }) {
  const [hidden, setHidden] = useState(() => new Set(INITIALLY_HIDDEN));

  useEffect(() => {
    if (!map) return;

    for (const group of LAYER_GROUPS) {
      const visibility = hidden.has(group.key) ? "none" : "visible";
      for (const id of group.layers) {
        // The layer only exists once the style has loaded.
        if (map.getLayer(id)) {
          map.setLayoutProperty(id, "visibility", visibility);
        }
      }
    }
  }, [map, hidden]);

  function toggle(key) {
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <details className="map-instrument map-layers" open={opensByDefault()}>
      <summary>Map layers</summary>

      <div className="map-instrument__body">
        {LAYER_GROUPS.map((group) => (
          <label key={group.key} className="map-layers__row">
            <input
              type="checkbox"
              checked={!hidden.has(group.key)}
              onChange={() => toggle(group.key)}
            />
            <span className="map-layers__swatch" style={{ background: group.swatch }} />
            <span>
              {group.label}
              {group.hint && <em> — {group.hint}</em>}
            </span>
          </label>
        ))}
      </div>
    </details>
  );
}
