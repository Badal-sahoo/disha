/**
 * F7 -- map canvas and state sync. The functions the whole dashboard is built
 * on top of.
 *
 * Owner: Track 2 - Day 1-2
 */
import { MAP_DEFAULTS, SOURCES } from "@/shared/utils/constants";

export function initMap(el, bounds) {
  // F7 - Create the MapLibre instance with EVERY GeoJSON source pre-registered
  //      and empty. Adding a source later forces a style reload and a visible
  //      flash mid-demo.
  //
  // IN :
  //   el     = HTMLElement          the container div
  //   bounds = {min_lon, min_lat, max_lon, max_lat} | null
  //            null -> use MAP_DEFAULTS.center / .zoom (Puri, zoom 10)
  //
  // OUT: maplibregl.Map
  //
  // USES:
  //   import maplibregl from "maplibre-gl"
  //   import "maplibre-gl/dist/maplibre-gl.css"        // or the pins render unstyled
  //   MAP_DEFAULTS = {style, center: [lon, lat], zoom}
  //   SOURCES      = {INCIDENTS, HEAT, RESOURCES, SHELTERS, ZONES,
  //                   ASSIGNMENTS, ALERTS, SUPPLY}
  //
  // DO, in this order, inside map.on("load"):
  //   1. for each id in SOURCES: map.addSource(id, {type:"geojson",
  //        data:{type:"FeatureCollection", features:[]}})
  //   2. add the layers that read them -- zones (fill) under alerts (fill)
  //      under assignments (line) under shelters/resources/incidents (symbol).
  //      Layer ORDER is paint order; pins must sit on top of fills.
  //   3. resolve/return only after "load" fires, or every later setData() is
  //      silently dropped.
  //
  // COORDINATE ORDER: MapLibre and GeoJSON want [lon, lat]. Everything else in
  // this project is (lat, lon). This function is the boundary -- flip here.
  throw new Error("TODO initMap -- Track 2 - Day 1");
}

export function applyDelta(event) {
  // F7 - Patch the live store by event type. Pure function over state, which is
  //      what makes the whole dashboard testable without a socket.
  //
  // IN :
  //   event = {
  //     type: str,   // "incident.new" | "incident.update" | "resource.update"
  //                  // | "assignment.new" | "assignment.update"
  //                  // | "shelter.update" | "zone.new" | "zone.removed"
  //                  // | "alert.new" | "kpi.update"
  //     data: obj,   // the SAME row shape that key has inside GET /api/state.
  //                  // "incident.update" may be PARTIAL: {id, corroborations}
  //                  // "zone.removed"    is just {id}
  //                  // "kpi.update"      is the whole kpi object, not a row
  //   }
  //
  // OUT: void -- mutates the live store:
  //   {
  //     t:           str,
  //     incidents:   [{id, code, lat, lon, kind, severity, people, cell_id,
  //                    corroborations, status, reported_at, first_response_at}],
  //     resources:   [{id, code, name, kind, lat, lon, capabilities, capacity,
  //                    speed_kmph, status, free_at}],
  //     shelters:    [{id, code, name, lat, lon, capacity, occupancy,
  //                    remaining, status}],
  //     zones:       [{id, lat, lon, radius_km, severity, source, active}],
  //     assignments: [{id, code, incident, resource, shelter, eta_min, gain,
  //                    policy, status, rescued_count, dispatched_at}],
  //     alerts:      [{id, identifier, event, severity, urgency, polygon,
  //                    sent_at, expires_at, active}],
  //     kpi:         {crit_mean, crit_p90, crit_sla_pct, unreached, awaiting},
  //   }
  //
  // USES:
  //   import { useLiveStore } from "@/shared/store/liveStore"
  //       useLiveStore.getState().upsert(collection, row)   // insert-or-merge on id
  //       useLiveStore.getState().remove(collection, id)
  //       useLiveStore.getState().patch({kpi})              // for kpi.update
  //   import { EVENT_TO_COLLECTION } from "@/shared/utils/constants"
  //       maps an event type straight to the collection name -- use it instead
  //       of a switch with ten cases
  //
  // THE ONE RULE: an "*.update" for an id the store does not hold means a delta
  // was missed. Call resyncFullState() instead of inserting the partial row --
  // inserting it leaves a half-populated object that renders as a pin with no
  // severity, and nothing errors.
  throw new Error("TODO applyDelta -- Track 2 - Day 1");
}

export function syncSources(map, state) {
  // F7 - Push store state into the map. One setData per layer.
  //
  // IN :
  //   map   = maplibregl.Map      from initMap
  //   state = the live store object above
  // OUT: void
  //
  // USES:
  //   toIncidentGeoJSON / toResourceGeoJSON / toShelterGeoJSON /
  //   toZoneGeoJSON / toAssignmentGeoJSON  from "@/shared/utils/geojson"
  //   map.getSource(SOURCES.X).setData(featureCollection)
  //
  // NEVER re-add a layer, only swap its data -- re-adding forces a style
  // reload. Throttle with requestAnimationFrame: a burst of fifty deltas should
  // repaint once, not fifty times.
  throw new Error("TODO syncSources -- Track 2 - Day 1");
}

export function resyncFullState(bbox) {
  // F7 - The reconciliation path that makes the delta stream safe.
  //
  // IN : bbox = {min_lon, min_lat, max_lon, max_lat} | null
  // OUT: Promise<state>  -- the GET /api/state body, already hydrated into the
  //                         store
  //
  // USES:
  //   fetchState(bbox)                        from "./api"
  //   useLiveStore.getState().hydrate(state)  from "@/shared/store/liveStore"
  //
  // CALLED ON: first mount, and from the socket's onOpen -- which fires on every
  // RECONNECT, not just the first connect. Skip that and the dashboard drifts
  // silently out of sync over a long demo: it looks fine, and it is wrong.
  throw new Error("TODO resyncFullState -- Track 2 - Day 1");
}

export function fitToBounds(map, bounds) {
  // F7 - Frame the district, or a subset of it.
  //
  // IN : map    = maplibregl.Map
  //      bounds = {min_lon, min_lat, max_lon, max_lat}
  // OUT: void
  //
  // map.fitBounds([[min_lon, min_lat], [max_lon, max_lat]], {padding: 40})
  throw new Error("TODO fitToBounds -- Track 2 - Day 2");
}

export function currentBbox(map) {
  // F7 - Read the viewport back, so /api/state and /api/reports/heatmap can be
  //      scoped to what the operator is actually looking at.
  //
  // IN : map = maplibregl.Map
  // OUT: {min_lon, min_lat, max_lon, max_lat}
  //
  // const b = map.getBounds() -> b.getWest(), b.getSouth(), b.getEast(), b.getNorth()
  throw new Error("TODO currentBbox -- Track 2 - Day 2");
}

export { MAP_DEFAULTS, SOURCES };
