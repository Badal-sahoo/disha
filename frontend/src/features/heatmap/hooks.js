/**
 * Owns the heat source: derives cells from the live store so the heat
 * follows every delta instead of going stale between requests.
 *
 * Visibility is not handled here -- the Map layers box switches it.
 */
import { useEffect } from "react";

import { useLiveStore } from "@/shared/store/liveStore";
import { SOURCES } from "@/shared/utils/constants";

import { heatCellsFrom, toHeatGeoJSON } from "./heat";

/** IN: map = maplibregl.Map | null */
export function useHeatLayer(map) {
  const incidents = useLiveStore((s) => s.incidents);

  useEffect(() => {
    if (!map) return;
    const cells = heatCellsFrom(incidents);
    map.getSource(SOURCES.HEAT)?.setData(toHeatGeoJSON(cells));
  }, [map, incidents]);
}
