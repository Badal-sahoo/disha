/**
 * the map itself. Creates the instance, hands it to the parent, cleans up.
 *
 * The basemap is always the standard one; the dashboard's dark/light theme does
 * not change it. Drawing lives in map.js and in each feature's own hook.
 */
import { useEffect, useRef, useState } from "react";

import { useSyncedMap } from "../hooks";
import { applyBasemapTheme, initMap } from "../map";

/**
 * PROPS:
 *   onMap = (map) => void   hands the instance up, so the zone editor and the
 *           layer components can attach to the same map
 */
export default function MapCanvas({ onMap }) {
  const containerRef = useRef(null);
  const [map, setMap] = useState(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;

    const instance = initMap(containerRef.current);

    // Hand the map up only once "load" has fired. initMap registers addOverlays
    // on that same event FIRST, so by the time this runs every source exists.
    // Publishing the instance synchronously is what used to lose the unit dots
    // and the dispatch lines: the feature hooks ran, found no source yet, and
    // `getSource(...)?.setData()` swallowed the miss without a word. Incidents
    // and shelters got away with it because addOverlays repaints them itself.
    instance.on("load", () => {
      setMap(instance);
      onMap?.(instance);
    });

    return () => instance.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useSyncedMap(map);

  // Knock the basemap tiles back to match the dashboard theme.
  //
  // ThemeToggle only sets data-theme on <html>; it has no idea a map exists, and
  // the map is not even on the same screen as the toggle. Watching the attribute
  // keeps the two in step without threading theme state through four components
  // that do not otherwise care about it.
  useEffect(() => {
    if (!map) return undefined;

    const root = document.documentElement;
    const sync = () => applyBasemapTheme(map, root.getAttribute("data-theme") ?? "dark");

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, [map]);

  return (
    <div className="map-canvas">
      <div ref={containerRef} className="map-canvas__gl" />
    </div>
  );
}
