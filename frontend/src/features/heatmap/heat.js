/**
 * F8 -- incident heatmap. Weighted by how much reports corroborate each other,
 * NOT by raw pin count.
 *
 * Owner: Track 2 - Day 2
 */
import { SOURCES } from "@/shared/utils/constants";

export function toHeatGeoJSON(cells) {
  // F8 - One point per grid cell, not per report.
  //
  // IN : cells = [{cell_id: str,   // "19.81,85.83"
  //                lat:     float, // cell centre
  //                lon:     float,
  //                weight:  float, // SUM(severity * corroborations)
  //                count:   int}]  // how many incidents rolled up
  //      -- straight from GET /api/reports/heatmap. You may also build it from
  //         the live store's incidents[] by grouping on cell_id, which keeps the
  //         heat in step with deltas without another request.
  //
  // OUT: {
  //        type: "FeatureCollection",
  //        features: [{
  //          type: "Feature",
  //          geometry: {type: "Point", coordinates: [lon, lat]},  // GeoJSON order
  //          properties: {cell_id, weight, count},
  //        }],
  //      }
  //
  // WHY CELLS: twenty reports of one flood must not look like twenty floods.
  // The cell is the unit of truth here; the pin layer (F7) shows individuals.
  throw new Error("TODO toHeatGeoJSON -- Track 2 - Day 2");
}

export function setHeatLayer(map, featureCollection) {
  // F8 - Push the collection into the pre-registered heat source.
  //
  // IN : map               = maplibregl.Map
  //      featureCollection = the object from toHeatGeoJSON
  // OUT: void
  //
  // USES: map.getSource(SOURCES.HEAT).setData(featureCollection)
  //
  // The LAYER is added once in initMap, as MapLibre's native "heatmap" type so
  // it is GPU-rendered. Wire it as:
  //   heatmap-weight    -> ["get", "weight"]  interpolated
  //   heatmap-radius    -> interpolate on zoom (12px at z8, 40px at z14)
  //   heatmap-intensity -> rises with zoom
  // Never add the layer here -- only swap its data.
  throw new Error("TODO setHeatLayer -- Track 2 - Day 2");
}

export function toggleHeat(map, on) {
  // F8 - Operators need the pins alone when reading individual reports.
  //      Give them the switch.
  //
  // IN : map = maplibregl.Map, on = bool
  // OUT: void
  //
  // map.setLayoutProperty("heat-layer", "visibility", on ? "visible" : "none")
  // Toggle VISIBILITY, never add/remove the layer -- removing forces a style
  // reload and the map visibly flashes.
  throw new Error("TODO toggleHeat -- Track 2 - Day 2");
}

export { SOURCES };
