/**
 * F8 -- renders no DOM of its own beyond the toggle; it drives a map layer.
 *
 * PROPS: map = maplibregl.Map | null
 */
import { useHeatLayer } from "../hooks";

export default function HeatLayer({ map }) {
  const { visible, setVisible } = useHeatLayer(map);

  return (
    <label className="map-toggle map-toggle--heat">
      <input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} />
      Heatmap
    </label>
  );
}
