/**
 * blocked zones. Three gestures and no more: press sets the centre,
 * drag sets the radius, a dropdown sets the severity.
 */
import { SEVERITY_COLORS, SOURCES } from "@/shared/utils/constants";
import { collection, haversineKm } from "@/shared/utils/geojson";

const KM_PER_DEGREE_LAT = 110.574;
const KM_PER_DEGREE_LON_AT_EQUATOR = 111.32;

/**
 * Turn a centre point and a radius into a polygon ring, because GeoJSON has no
 * circle shape.
 *
 * OUT: [[lon, lat], ...] with the first corner repeated at the end. A ring that
 *      does not close renders as a wedge, and it is never obvious why.
 *
 * A degree of longitude gets shorter as you move away from the equator, so the
 * east-west step is divided by cos(latitude). Skip that and the circle comes
 * out as an ellipse.
 */
export function circleToPolygon(lat, lon, radiusKm, corners = 64) {
  const latitudeInRadians = (lat * Math.PI) / 180;
  const degreesLatPerKm = 1 / KM_PER_DEGREE_LAT;
  const degreesLonPerKm =
    1 / (KM_PER_DEGREE_LON_AT_EQUATOR * Math.cos(latitudeInRadians) || 1);

  const ring = [];
  for (let corner = 0; corner < corners; corner += 1) {
    const angle = (corner / corners) * 2 * Math.PI;
    const east = radiusKm * degreesLonPerKm * Math.cos(angle);
    const north = radiusKm * degreesLatPerKm * Math.sin(angle);
    ring.push([lon + east, lat + north]);   // GeoJSON order: lon first
  }

  ring.push(ring[0]);   // close the ring
  return ring;
}

/** One filled circle per active zone. */
export function toZoneGeoJSON(zones = []) {
  const shapes = [];

  for (const zone of zones) {
    if (zone.active === false) continue;

    shapes.push({
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [circleToPolygon(zone.lat, zone.lon, zone.radius_km)],
      },
      properties: {
        id: zone.id,
        severity: zone.severity,
        source: zone.source,
        color: SEVERITY_COLORS[zone.severity] ?? SEVERITY_COLORS[3],
      },
    });
  }

  return collection(shapes);
}

export function renderZones(map, zones) {
  map?.getSource(SOURCES.ZONES)?.setData(toZoneGeoJSON(zones));
}

/**
 * Put the map into draw mode: press, drag out a radius, release.
 *
 * IN : onComplete = ({lat, lon, radius_km}) => void   severity is picked in the
 *      form afterwards, not here.
 * OUT: {cancel} -- ALWAYS call it when leaving draw mode, or the handlers stay
 *      attached and the next ordinary map click starts another zone.
 *
 * MapLibre reports positions as event.lngLat, which is lon first. They are
 * converted to (lat, lon) before anything leaves this function.
 */
export function startZoneDraw(map, onComplete) {
  if (!map) return { cancel() {} };

  const canvas = map.getCanvas();
  const cursorBefore = canvas.style.cursor;
  canvas.style.cursor = "crosshair";

  let centre = null;

  function showPreview(radiusKm) {
    map.getSource(SOURCES.ZONES)?.setData(
      collection([
        {
          type: "Feature",
          geometry: {
            type: "Polygon",
            coordinates: [circleToPolygon(centre.lat, centre.lon, radiusKm)],
          },
          properties: { id: "draft", severity: 3, color: SEVERITY_COLORS[3] },
        },
      ])
    );
  }

  function radiusTo(event) {
    return haversineKm(centre.lat, centre.lon, event.lngLat.lat, event.lngLat.lng);
  }

  function handlePress(event) {
    centre = { lat: event.lngLat.lat, lon: event.lngLat.lng };
    // Without this, dragging out the radius pans the map underneath you.
    map.dragPan.disable();
  }

  function handleDrag(event) {
    if (!centre) return;
    showPreview(radiusTo(event));
  }

  function handleRelease(event) {
    if (!centre) return;

    const draft = {
      lat: centre.lat,
      lon: centre.lon,
      radius_km: Math.max(radiusTo(event), 0.2),   // a stray click is not a zone
    };

    centre = null;
    cancel();
    onComplete?.(draft);
  }

  function cancel() {
    canvas.style.cursor = cursorBefore;
    map.dragPan.enable();
    map.off("mousedown", handlePress);
    map.off("mousemove", handleDrag);
    map.off("mouseup", handleRelease);
  }

  map.on("mousedown", handlePress);
  map.on("mousemove", handleDrag);
  map.on("mouseup", handleRelease);

  return { cancel };
}

export { SEVERITY_COLORS, SOURCES };
