/**
 * F7 -- the map itself. Fully wired: it creates the instance, keeps sources in
 * step and cleans up. The drawing decisions live in map.js.
 */
import { useEffect, useRef, useState } from "react";

import { useSyncedMap } from "../hooks";
import { initMap } from "../map";

/**
 * PROPS:
 *   bounds   = {min_lon, min_lat, max_lon, max_lat} | null
 *   onMap    = (map) => void   optional; hands the instance to a parent so the
 *              zone editor and fleet layer can attach to the same map
 */
export default function MapCanvas({ bounds = null, onMap }) {
  const containerRef = useRef(null);
  const [map, setMap] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!containerRef.current) return;
    let instance = null;
    try {
      instance = initMap(containerRef.current, bounds);
      setMap(instance);
      onMap?.(instance);
    } catch (e) {
      // initMap is a stub until Track 2 fills it in -- show that plainly
      // instead of a blank white rectangle nobody can diagnose.
      setError(e.message);
    }
    return () => instance?.remove?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useSyncedMap(map);

  return (
    <div className="map-canvas">
      <div ref={containerRef} className="map-canvas__gl" />
      {error && <div className="map-canvas__placeholder">{error}</div>}
    </div>
  );
}
