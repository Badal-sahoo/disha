/**
 * F9 -- drives map layers, renders nothing itself.
 *
 * PROPS: map = maplibregl.Map | null
 */
import { useFleetLayer } from "../hooks";

export default function FleetLayer({ map }) {
  useFleetLayer(map);
  return null;
}
