/**
 * F12 -- three gestures: click sets the centre, drag sets the radius, a picker
 * sets severity. Keep it to three.
 *
 * Owner: Track 2 - Day 4
 */
import { SEVERITY_COLORS, SOURCES } from "@/shared/utils/constants";

export function startZoneDraw(map, onComplete) {
  // F12 - Put the map into draw mode.
  //
  // IN : map        = maplibregl.Map
  //      onComplete = (draft) => void
  //                   draft = {lat: float, lon: float, radius_km: float}
  //                           severity is chosen in the UI afterwards, not here
  // OUT: {cancel: () => void}   -- ALWAYS return this. Without it the mousedown
  //                                handler outlives draw mode and the next
  //                                ordinary map click starts a new zone.
  //
  // DO:
  //   map.getCanvas().style.cursor = "crosshair"
  //   mousedown  -> record centre [lng, lat]
  //   mousemove  -> radius = haversine(centre, cursor); paint a preview circle
  //   mouseup    -> onComplete({lat, lon, radius_km}); tear the handlers down
  //   map.dragPan.disable() during the drag, and re-enable it in cancel(), or
  //   dragging out the radius pans the map underneath you.
  //
  // A MapLibre event gives you e.lngLat.lng / e.lngLat.lat -- lon first. Convert
  // to (lat, lon) before it leaves this module.
  throw new Error("TODO startZoneDraw -- Track 2 - Day 4");
}

export function renderZones(map, zones) {
  // F12 - Draw the cut areas.
  //
  // IN : map   = maplibregl.Map
  //      zones = [{id, lat, lon, radius_km, severity, source, active}]
  // OUT: void
  //
  // A circle of radius_km is a POLYGON in GeoJSON -- approximate it with 64
  // points around the centre (metres per degree of longitude shrinks by
  // cos(lat), so scale the x offset or your circles come out as ellipses).
  //
  // Severity 5 gets a hard hatched edge; 1-4 get a soft fill from
  // SEVERITY_COLORS. The visual difference between "slow" and "gone" must be
  // obvious at a glance -- that distinction IS the feature.
  //
  // map.getSource(SOURCES.ZONES).setData(featureCollection)
  throw new Error("TODO renderZones -- Track 2 - Day 4");
}

export function circleToPolygon(lat, lon, radiusKm, steps = 64) {
  // F12 - Helper: a circle as a GeoJSON polygon ring.
  //
  // IN : lat, lon = float, radiusKm = float, steps = int
  // OUT: [[lon, lat], ...]   -- GeoJSON order, first point repeated at the end
  //                             to close the ring (a ring that does not close
  //                             renders as a wedge)
  throw new Error("TODO circleToPolygon -- Track 2 - Day 4");
}

export { SEVERITY_COLORS, SOURCES };
