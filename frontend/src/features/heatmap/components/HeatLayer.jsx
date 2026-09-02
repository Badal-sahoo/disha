/**
 * renders nothing. It keeps the heat source in step with the store.
 *
 * Showing and hiding the layer is the Map layers box's job now.
 *
 * PROPS: map = maplibregl.Map | null
 */
import { useHeatLayer } from "../hooks";

export default function HeatLayer({ map }) {
  useHeatLayer(map);
  return null;
}
