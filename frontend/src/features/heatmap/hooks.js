/**
 * F8 hooks. Wired: it derives heat from the live store so the layer follows
 * deltas without a second request. The transform itself is the stub in heat.js.
 */
import { useEffect, useState } from "react";

import { useLiveStore } from "@/shared/store/liveStore";

import { setHeatLayer, toHeatGeoJSON, toggleHeat } from "./heat";

/**
 * Keep the heat layer in step with incidents, and expose the on/off switch.
 *
 * IN : map = maplibregl.Map | null
 * OUT: {visible: bool, setVisible: (bool) => void}
 */
export function useHeatLayer(map) {
  const incidents = useLiveStore((s) => s.incidents);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (!map) return;
    try {
      // Group incidents into cells client-side, so the heat follows every
      // delta rather than going stale between /api/reports/heatmap calls.
      const byCell = new Map();
      for (const inc of incidents) {
        if (inc.status === "RESOLVED") continue;
        const cell = byCell.get(inc.cell_id) ?? {
          cell_id: inc.cell_id,
          lat: inc.lat,
          lon: inc.lon,
          weight: 0,
          count: 0,
        };
        cell.weight += (inc.severity ?? 1) * (inc.corroborations ?? 1);
        cell.count += 1;
        byCell.set(inc.cell_id, cell);
      }
      setHeatLayer(map, toHeatGeoJSON([...byCell.values()]));
    } catch {
      /* stub not filled in yet */
    }
  }, [map, incidents]);

  useEffect(() => {
    if (!map) return;
    try {
      toggleHeat(map, visible);
    } catch {
      /* stub not filled in yet */
    }
  }, [map, visible]);

  return { visible, setVisible };
}
