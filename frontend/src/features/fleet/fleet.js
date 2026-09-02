/**
 * turning units and dispatches into map data.
 */
import { STATUS_COLORS } from "@/shared/utils/constants";
import { collection, line, point } from "@/shared/utils/geojson";

/**
 * One dot per unit: colour by status, so the map is readable without a legend.
 *
 * Colours come from STATUS_COLORS rather than hexes typed in here, or the map
 * and the roster panel slowly drift apart.
 */
export function toResourceGeoJSON(resources = []) {
  const dots = resources.map((r) =>
    point(r.lat, r.lon, {
      id: r.id,
      code: r.code,
      kind: r.kind,
      status: r.status,
      capacity: r.capacity,
      color: STATUS_COLORS[r.status] ?? STATUS_COLORS.IDLE,
    })
  );
  return collection(dots);
}

/**
 * One line per live dispatch, from the unit to the incident.
 *
 * If the assignment carries a routed polyline, use it. A straight line drawn
 * across a flooded river undoes the whole point of routing around the water.
 */
export function toAssignmentGeoJSON(assignments = []) {
  const lines = [];
  for (const a of assignments) {
    if (a.incident_lat == null) continue;

    // Draw from where the unit SET OUT, not where it is now.
    //
    // Committing a dispatch moves the unit to its destination so the next plan
    // starts from the right place, which means resource_lat/lon is the END of
    // the journey. Using it drew every route as a line from the destination to
    // itself -- zero length, invisible, and the map looked empty after a
    // dispatch. origin_lat/lon is the start; fall back for PROPOSED rows and
    // for any row written before the field existed.
    const startLat = a.origin_lat ?? a.resource_lat;
    const startLon = a.origin_lon ?? a.resource_lon;
    if (startLat == null) continue;

    const path = a.polyline?.length
      ? a.polyline
      : [[startLat, startLon], [a.incident_lat, a.incident_lon]];

    lines.push(line(path, { code: a.code, status: a.status, eta_min: a.eta_min }));
  }
  return collection(lines);
}

/**
 * Capacity bars for the shelter panel.
 *
 * Returns plain data, not JSX, so the thresholds can be checked without
 * rendering a component. ShelterBars.jsx draws whatever comes back.
 */
export function renderShelterBars(shelters = []) {
  return shelters.map((s) => {
    const pct = s.capacity ? Math.min((s.occupancy / s.capacity) * 100, 100) : 0;

    let tone = "ok";
    if (s.status === "INACCESSIBLE") tone = "closed";
    else if (pct >= 100) tone = "full";
    else if (pct >= 80) tone = "warn";

    return {
      id: s.id,
      code: s.code,
      name: s.name,
      pct: Math.round(pct * 10) / 10,
      tone,
      label: `${s.occupancy} / ${s.capacity}`,
    };
  });
}
