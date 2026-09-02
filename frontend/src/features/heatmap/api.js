/**
 * the heatmap endpoint. Fully implemented.
 */
import { api } from "@/shared/api/client";

/**
 * GET /api/reports/heatmap
 *
 * IN : bbox = {min_lon, min_lat, max_lon, max_lat} | null
 * OUT: Promise<[{
 *        cell_id: str,    // "19.81,85.83"  (lat/lon rounded to 2dp, ~1.1 km)
 *        lat:     float,  // cell centre
 *        lon:     float,
 *        weight:  float,  // SUM(severity * corroborations) across the cell
 *        count:   int,    // incidents rolled up into this cell
 *      }]>
 */
export function fetchHeatmap(bbox = null) {
  const params = bbox
    ? { bbox: [bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat].join(",") }
    : {};
  return api.get("/reports/heatmap", { params }).then((r) => r.data);
}
