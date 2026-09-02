/**
 * Ties the socket, the resync path and the live store together.
 */
import { useEffect, useRef } from "react";

import { connectOps } from "@/shared/api/socket";
import { useLiveStore } from "@/shared/store/liveStore";

import { applyDelta, resyncFullState, syncSources } from "./map";

/**
 * Open /ws/ops, apply every delta, and resync on every reconnect.
 *
 * IN : bbox = {min_lon, min_lat, max_lon, max_lat} | null
 * OUT: {connected: bool}
 *
 * The onOpen -> resyncFullState() line is the important one. It fires on the
 * FIRST connect and on every reconnect after a drop, which is what stops the
 * dashboard drifting out of sync when the socket blips mid-demo.
 */
export function useOpsSocket(bbox = null) {
  const connected = useLiveStore((s) => s.connected);
  const setConnected = useLiveStore((s) => s.setConnected);
  const bboxRef = useRef(bbox);
  bboxRef.current = bbox;

  useEffect(() => {
    const channel = connectOps({
      onOpen: () => {
        setConnected(true);
        resyncFullState(bboxRef.current);
      },
      onEvent: (event) => {
        if (event.type === "connected") return; // handshake ack, not a delta
        applyDelta(event);
      },
      onClose: () => setConnected(false),
    });
    return () => channel.close();
  }, [setConnected]);

  return { connected };
}

/**
 * Keep the MapLibre sources in step with the store.
 *
 * IN : map = maplibregl.Map | null
 * OUT: void
 *
 * Subscribes to the whole store rather than a slice on purpose: syncSources
 * throttles to one repaint per frame, so one subscription is cheaper than six.
 */
export function useSyncedMap(map) {
  useEffect(() => {
    if (!map) return;
    syncSources(map, useLiveStore.getState());
    return useLiveStore.subscribe((state) => syncSources(map, state));
  }, [map]);
}

/**
 * Poll GET /api/state on an interval.
 *
 * IN : intervalMs = int | null   -- null disables it
 *      bbox       = bbox | null
 * OUT: void
 *
 * NOT used by default: the socket is the live path. This exists as the escape
 * hatch the blueprint recommends -- if Channels or Redis misbehaves on the day,
 * set an interval here and the dashboard keeps working with nothing else
 * changed. Two seconds is the documented cadence.
 */
export function useStatePolling(intervalMs = null, bbox = null) {
  useEffect(() => {
    if (!intervalMs) return;
    const id = setInterval(() => resyncFullState(bbox), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, bbox]);
}
