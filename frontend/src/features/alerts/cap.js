/**
 * drawing CAP warning areas on the map.
 */
import { CAP_SEVERITY_COLORS, SOURCES } from "@/shared/utils/constants";
import { collection, polygon } from "@/shared/utils/geojson";

/**
 * Draw every active warning polygon.
 *
 * alert.polygon is [[lat, lon], ...] -- lat first, the way CAP writes it.
 * geojson.polygon() flips it to [lon, lat] and closes the ring; an unclosed
 * ring renders as a wedge and it is never obvious why.
 */
export function renderCapPolygon(map, alerts = []) {
  const shapes = [];

  for (const a of alerts) {
    if (a.active === false) continue;
    if (!a.polygon || a.polygon.length < 3) continue;

    shapes.push(
      polygon(a.polygon, {
        id: a.id,
        event: a.event,
        severity: a.severity,
        color: CAP_SEVERITY_COLORS[a.severity] ?? "#f76707",
      })
    );
  }

  map?.getSource(SOURCES.ALERTS)?.setData(collection(shapes));
}

export { CAP_SEVERITY_COLORS, SOURCES };
