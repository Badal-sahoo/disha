/**
 * The ONE place (lat, lon) becomes [lon, lat].
 *
 * Everything in this project names coordinates lat and lon, in that order.
 * GeoJSON and MapLibre want the opposite. Converting anywhere else is how the
 * whole district ends up in the Bay of Bengal -- so every flip lives here.
 *
 * Owner: Track 2 - Day 1
 */
import { SEVERITY_COLORS, SHELTER_COLORS } from "./constants";

/**
 */

/**
 * IN : lat, lon = float
 * OUT: [lon, lat]      -- GeoJSON position. Implemented; it is one line and
 *                         everything below depends on it.
 */
export const pos = (lat, lon) => [lon, lat];

/**
 * IN : coordinates = [lon, lat]
 * OUT: {lat, lon}
 */
export const fromPos = ([lon, lat]) => ({ lat, lon });

/**
 * IN : features = [Feature, ...]
 * OUT: {type: "FeatureCollection", features}
 */
export const collection = (features = []) => ({ type: "FeatureCollection", features });

/**
 * IN : lat, lon = float, properties = obj
 * OUT: {type: "Feature", geometry: {type: "Point", coordinates: [lon, lat]}, properties}
 */
export const point = (lat, lon, properties = {}) => ({
  type: "Feature",
  geometry: { type: "Point", coordinates: pos(lat, lon) },
  properties,
});

/**
 * IN : path       = [[lat, lon], ...]
 *      properties = obj
 * OUT: {type: "Feature", geometry: {type: "LineString", coordinates: [[lon, lat], ...]}, properties}
 */
export const line = (path, properties = {}) => ({
  type: "Feature",
  geometry: { type: "LineString", coordinates: path.map(([lat, lon]) => pos(lat, lon)) },
  properties,
});

/**
 * IN : ring       = [[lat, lon], ...]   -- open or closed
 *      properties = obj
 * OUT: {type: "Feature", geometry: {type: "Polygon", coordinates: [[[lon, lat], ...]]}, properties}
 *
 * Closes the ring automatically. An unclosed ring renders as a wedge, and it is
 * never obvious why.
 */
export const polygon = (ring, properties = {}) => {
  const coords = ring.map(([lat, lon]) => pos(lat, lon));
  const [first] = coords;
  const last = coords[coords.length - 1];
  if (first && last && (first[0] !== last[0] || first[1] !== last[1])) coords.push(first);
  return {
    type: "Feature",
    geometry: { type: "Polygon", coordinates: [coords] },
    properties,
  };
};

/**
 * Great-circle distance. Mirrors dispatch/engine.py haversine_km.
 *
 * IN : lat1, lon1, lat2, lon2 = float
 * OUT: float -- kilometres
 */
export function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const rad = (d) => (d * Math.PI) / 180;
  const dLat = rad(lat2 - lat1);
  const dLon = rad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

/**
 * IN : points = [{lat, lon}, ...]
 * OUT: {min_lon, min_lat, max_lon, max_lat} | null   -- null for an empty list
 */
export function boundsOf(points) {
  if (!points.length) return null;
  return points.reduce(
    (b, p) => ({
      min_lon: Math.min(b.min_lon, p.lon),
      min_lat: Math.min(b.min_lat, p.lat),
      max_lon: Math.max(b.max_lon, p.lon),
      max_lat: Math.max(b.max_lat, p.lat),
    }),
    { min_lon: 180, min_lat: 90, max_lon: -180, max_lat: -90 }
  );
}

// --- collection builders. Colour lives with the geometry so the paint
// --- expressions can just read ["get", "color"].

/** IN: incidents = [{id, lat, lon, severity, ...}] -- OUT: FeatureCollection */
export const toIncidentGeoJSON = (incidents = []) =>
  collection(
    incidents.map((i) =>
      point(i.lat, i.lon, {
        id: i.id, code: i.code, kind: i.kind, severity: i.severity,
        people: i.people, status: i.status,
        color: SEVERITY_COLORS[i.severity] ?? SEVERITY_COLORS[3],
      })
    )
  );

/**
 * One point per SCENE, for the zoomed-out view.
 *
 * Thirty families reporting one flooded village are thirty pins. Zoomed out
 * they pile into an unreadable blob; zoomed in they are exactly what a boat
 * crew needs, because the route has to reach each house. So the map draws both
 * and swaps between them by zoom -- scenes far out, families close in. See the
 * incidents-scene / incidents-point layers in features/map/map.js.
 *
 * Grouped by (cell_id, kind), the same key services/clustering.py uses on the
 * server, so one circle here is exactly one dispatch card there.
 *
 * IN : incidents = [{lat, lon, cell_id, kind, severity, people, status, code}]
 * OUT: FeatureCollection of one point per scene, at the mean of its reports
 */
export function toSceneGeoJSON(incidents = []) {
  const scenes = new Map();

  for (const i of incidents) {
    const key = `${i.cell_id ?? i.id}|${i.kind}`;
    let scene = scenes.get(key);
    if (!scene) {
      scene = { key, rows: [], code: i.code, severity: 0, people: 0, open: 0 };
      scenes.set(key, scene);
    }
    scene.rows.push(i);
    scene.severity = Math.max(scene.severity, i.severity ?? 0);
    scene.people += i.people ?? 0;
    if (i.status === "OPEN") scene.open += 1;
    // Oldest code names the scene, matching the dispatch card.
    if (i.code && i.code < scene.code) scene.code = i.code;
  }

  return collection(
    [...scenes.values()].map((scene) =>
      point(
        scene.rows.reduce((sum, r) => sum + r.lat, 0) / scene.rows.length,
        scene.rows.reduce((sum, r) => sum + r.lon, 0) / scene.rows.length,
        {
          code: scene.code,
          kind: scene.rows[0].kind,
          severity: scene.severity,
          people: scene.people,
          families: scene.rows.length,
          status: scene.open ? "OPEN" : "ASSIGNED",
          color: SEVERITY_COLORS[scene.severity] ?? SEVERITY_COLORS[3],
        }
      )
    )
  );
}

/** IN: shelters = [{id, lat, lon, capacity, occupancy, status}] -- OUT: FeatureCollection */
export const toShelterGeoJSON = (shelters = []) =>
  collection(
    shelters.map((s) =>
      point(s.lat, s.lon, {
        id: s.id, code: s.code, name: s.name, kind: s.kind,
        capacity: s.capacity, occupancy: s.occupancy, remaining: s.remaining,
        status: s.status,
        color: SHELTER_COLORS[s.status] ?? SHELTER_COLORS.INACCESSIBLE,
      })
    )
  );
