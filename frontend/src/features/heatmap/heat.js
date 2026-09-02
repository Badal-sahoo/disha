/**
 * the incident heatmap.
 *
 * Weighted by how much reports back each other up, not by raw pin count:
 * twenty reports of one flood must not look like twenty floods.
 */
import { SOURCES } from "@/shared/utils/constants";
import { collection, point } from "@/shared/utils/geojson";

/**
 * Group open incidents into their grid cells.
 *
 * Done from the live store rather than by calling /api/reports/heatmap, so the
 * heat follows every socket delta instead of going stale between requests.
 *
 * IN : incidents = [{cell_id, severity, corroborations, status}]
 * OUT: [{cell_id, lat, lon, weight, count}]
 */
export function heatCellsFrom(incidents = []) {
  const cells = new Map();

  for (const inc of incidents) {
    if (inc.status !== "OPEN" || !inc.cell_id) continue;

    let cell = cells.get(inc.cell_id);
    if (!cell) {
      // cell_id is "19.81,85.83" -- the centre of the cell.
      const [lat, lon] = inc.cell_id.split(",").map(Number);
      cell = { cell_id: inc.cell_id, lat, lon, weight: 0, count: 0 };
      cells.set(inc.cell_id, cell);
    }

    cell.weight += (inc.severity ?? 1) * (inc.corroborations ?? 1);
    cell.count += 1;
  }

  return [...cells.values()];
}

/** One point per cell, ready for the heatmap layer. */
export function toHeatGeoJSON(cells = []) {
  const points = cells.map((c) =>
    point(c.lat, c.lon, { cell_id: c.cell_id, weight: c.weight, count: c.count })
  );
  return collection(points);
}

export { SOURCES };
