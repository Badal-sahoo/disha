/**
 * Owns the unit dots and the dispatch lines.
 */
import { useEffect, useMemo } from "react";

import { useLiveStore } from "@/shared/store/liveStore";
import { SOURCES } from "@/shared/utils/constants";

import { renderShelterBars, toAssignmentGeoJSON, toResourceGeoJSON } from "./fleet";

/** IN: map = maplibregl.Map | null */
export function useFleetLayer(map) {
  const resources = useLiveStore((s) => s.resources);
  const assignments = useLiveStore((s) => s.assignments);

  useEffect(() => {
    if (!map) return;

    map.getSource(SOURCES.RESOURCES)?.setData(toResourceGeoJSON(resources));

    // Only draw work that is actually happening. A PROPOSED row is a preview
    // no unit has been told about, and a COMPLETE one is over.
    const live = assignments.filter(
      (a) => a.status !== "PROPOSED" && a.status !== "COMPLETE"
    );
    map.getSource(SOURCES.ASSIGNMENTS)?.setData(toAssignmentGeoJSON(live));
  }, [map, resources, assignments]);
}

/** OUT: [{id, code, name, pct, tone, label}] for the shelter panel. */
export function useShelterBars() {
  const shelters = useLiveStore((s) => s.shelters);
  return useMemo(() => renderShelterBars(shelters), [shelters]);
}
