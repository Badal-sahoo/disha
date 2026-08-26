/**
 * F13 -- rendering CAP impact polygons.
 *
 * Owner: Track 2 - Day 5
 */
import { CAP_SEVERITY_COLORS, SOURCES } from "@/shared/utils/constants";

export function renderCapPolygon(map, alerts) {
  // F13 - The CAP area polygon as a map overlay.
  //
  // IN : map    = maplibregl.Map
  //      alerts = [{id, identifier, event, severity, urgency, polygon, active}]
  //               polygon is [[lat, lon], ...] -- LAT FIRST
  // OUT: void
  //
  // OUT (the FeatureCollection you build):
  //   {
  //     type: "FeatureCollection",
  //     features: [{
  //       type: "Feature",
  //       geometry: {type: "Polygon", coordinates: [[[lon, lat], ...]]},
  //       properties: {id, event, severity,
  //                    color: CAP_SEVERITY_COLORS[severity]},
  //     }],
  //   }
  //
  // FLIP the coordinate order here -- this is the GeoJSON boundary. And CLOSE
  // the ring: repeat the first point at the end, or MapLibre renders a wedge.
  //
  // STYLE IT DIFFERENTLY from an incident. A CAP polygon is a PREDICTED impact
  // zone, not something anyone has observed -- dashed outline, low-opacity
  // fill. Confusing the two on stage undermines the whole early-warning story.
  //
  // map.getSource(SOURCES.ALERTS).setData(featureCollection)
  throw new Error("TODO renderCapPolygon -- Track 2 - Day 5");
}

export function checkGeofence(loc, alerts) {
  // F13 - Does this point fall inside any active warning polygon?
  //
  // IN : loc    = {lat: float, lon: float}
  //      alerts = [{id, polygon: [[lat, lon], ...], ...}]
  // OUT: [alert, ...]   -- every alert whose polygon contains the point, [] if none
  //
  // Ray casting, about twelve lines, no geo library. Mirrors
  // alerts.services.point_in_polygon on the backend -- keep the two in step or
  // the app and the server disagree about who gets warned.
  //
  // Remember the wrap-around edge (last vertex back to the first). Forgetting
  // it only breaks points near one side, which is why it survives testing.
  throw new Error("TODO checkGeofence -- Track 2 - Day 5");
}

export { CAP_SEVERITY_COLORS, SOURCES };
