/**
 * F9 hooks. Wired to the live store; the transforms are the stubs in fleet.js.
 */
import { useEffect, useMemo } from "react";

import { useLiveStore } from "@/shared/store/liveStore";
import { SOURCES } from "@/shared/utils/constants";

import { renderShelterBars, toAssignmentGeoJSON, toResourceGeoJSON } from "./fleet";

/**
 * Keep the unit and assignment-line sources in step with the store.
 *
 * IN : map = maplibregl.Map | null
 * OUT: void
 */
export function useFleetLayer(map) {
  const resources = useLiveStore((s) => s.resources);
  const assignments = useLiveStore((s) => s.assignments);

  useEffect(() => {
    if (!map) return;
    try {
      map.getSource(SOURCES.RESOURCES)?.setData(toResourceGeoJSON(resources));
      const live = assignments.filter((a) => a.status !== "PROPOSED" && a.status !== "COMPLETE");
      map.getSource(SOURCES.ASSIGNMENTS)?.setData(toAssignmentGeoJSON(live));
    } catch {
      /* stubs not filled in yet */
    }
  }, [map, resources, assignments]);
}

/**
 * IN : --
 * OUT: [{id, code, name, pct, tone, label}]  -- [] until the stub is written
 */
export function useShelterBars() {
  const shelters = useLiveStore((s) => s.shelters);
  return useMemo(() => {
    try {
      return renderShelterBars(shelters);
    } catch {
      return [];
    }
  }, [shelters]);
}
