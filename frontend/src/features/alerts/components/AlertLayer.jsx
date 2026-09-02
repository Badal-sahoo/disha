/**
 * Keeps the CAP impact polygons on the map, renders nothing itself.
 *
 * Same null-rendering pattern as FleetLayer and HeatLayer. It exists because the
 * warnings LIST now lives on its own page: without this, walking away from the
 * Incoming section would quietly take the dashed warning areas off the map.
 *
 * PROPS: map = maplibregl.Map | null
 */
import { useAlerts } from "../hooks";

export default function AlertLayer({ map }) {
  useAlerts(map);
  return null;
}
