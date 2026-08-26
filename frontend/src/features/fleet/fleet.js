/**
 * F9 -- the layer that makes the map feel alive. Where every unit is, what it
 * is doing, and where it is going.
 *
 * Owner: Track 2 - Day 3
 */
import { SOURCES, STATUS_COLORS } from "@/shared/utils/constants";

export function toResourceGeoJSON(resources) {
  // F9 - Icon by kind, colour by status. State readable at a glance, with no
  //      legend lookup.
  //
  // IN : resources = [{id, code, name, kind, lat, lon, capabilities, capacity,
  //                    speed_kmph, status, free_at, base_name}]
  //      kind   is "TEAM" | "BOAT" | "TRUCK" | "AMBULANCE"
  //      status is "IDLE" | "ENROUTE" | "ONSCENE" | "TRANSPORTING"
  //             | "OUT_OF_SERVICE"
  //
  // OUT: {
  //        type: "FeatureCollection",
  //        features: [{
  //          type: "Feature",
  //          geometry: {type: "Point", coordinates: [lon, lat]},
  //          properties: {id, code, kind, status, capacity,
  //                       color: STATUS_COLORS[status],
  //                       icon:  kind.toLowerCase()},   // matches the sprite name
  //        }],
  //      }
  //
  // STATUS_COLORS is already imported -- read the colour from there rather than
  // retyping hexes, or the map and the roster panel drift apart.
  throw new Error("TODO toResourceGeoJSON -- Track 2 - Day 3");
}

export function toAssignmentGeoJSON(assignments) {
  // F9 - One line per live dispatch, unit -> incident.
  //
  // IN : assignments = [{id, code, resource_lat, resource_lon, incident_lat,
  //                      incident_lon, status, eta_min, polyline?}]
  //      polyline, when present, is [[lat, lon], ...] from GET /api/route
  //
  // OUT: {
  //        type: "FeatureCollection",
  //        features: [{
  //          type: "Feature",
  //          geometry: {type: "LineString", coordinates: [[lon, lat], ...]},
  //          properties: {code, status, eta_min},
  //        }],
  //      }
  //
  // USE THE ROUTED POLYLINE when the assignment carries one. A straight line
  // drawn over a flooded river undoes the entire routing story you are on stage
  // to tell. Fall back to the two-point segment only when polyline is absent.
  throw new Error("TODO toAssignmentGeoJSON -- Track 2 - Day 3");
}

export function drawAssignmentLine(map, assignment) {
  // F9 - Add or replace ONE line, without rebuilding the whole collection.
  //
  // IN : map        = maplibregl.Map
  //      assignment = one row of the shape above
  // OUT: void
  //
  // Read the current source data, upsert the feature by `code`, setData back.
  // Used when a single assignment.new delta arrives -- rebuilding every line on
  // each delta is what makes a busy map stutter.
  throw new Error("TODO drawAssignmentLine -- Track 2 - Day 3");
}

export function animateUnit(map, id, path, durationMs) {
  // F9 - Interpolate a marker between GPS pings so movement looks continuous at
  //      a 20-second beacon interval.
  //
  // IN : map        = maplibregl.Map
  //      id         = int|str    the resource id
  //      path       = [[lat, lon], [lat, lon]]   from-position to new-position
  //      durationMs = int        match the beacon interval, 20000
  // OUT: {cancel: () => void}    -- ALWAYS return this and call it when a newer
  //                                 ping arrives, or two animations fight over
  //                                 the same marker and it visibly jitters
  //
  // requestAnimationFrame, linear interpolation, then setData on the resources
  // source with the interpolated coordinate.
  throw new Error("TODO animateUnit -- Track 2 - Day 3");
}

export function renderShelterBars(shelters) {
  // F9 - Capacity fill bars. The moment a judge sees a constraint actually bind.
  //
  // IN : shelters = [{id, code, name, capacity, occupancy, remaining, status}]
  // OUT: [{
  //        id:      int,
  //        code:    str,
  //        name:    str,
  //        pct:     float,   // 0..100, occupancy / capacity
  //        tone:    str,     // "ok" under 80, "warn" 80-99, "full" at 100,
  //                          //   "closed" when status is INACCESSIBLE
  //        label:   str,     // "412 / 600"
  //      }]
  //
  // A view-model, not JSX -- ShelterBars.jsx renders whatever this returns, so
  // the thresholds stay testable without mounting a component.
  throw new Error("TODO renderShelterBars -- Track 2 - Day 3");
}

export { SOURCES, STATUS_COLORS };
