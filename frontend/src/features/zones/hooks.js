/**
 * F12 hooks. Wired: create/delete round-trip to the API and the resulting
 * broadcast re-renders every dashboard. The drawing geometry is the stub.
 */
import { useCallback, useEffect, useState } from "react";

import { toApiError } from "@/shared/api/client";
import { useLiveStore } from "@/shared/store/liveStore";

import { createZone as createZoneRequest, deleteZone as deleteZoneRequest } from "./api";
import { renderZones, startZoneDraw } from "./draw";

/**
 * IN : map = maplibregl.Map | null
 * OUT: {
 *        zones:     [zone, ...],
 *        drawing:   bool,
 *        pending:   bool,
 *        error:     obj|null,
 *        beginDraw: (severity) => void,   // enters draw mode; on completion it
 *                                         //   POSTs with the given severity
 *        cancelDraw:() => void,
 *        remove:    (id) => Promise<void>,
 *      }
 */
export function useZones(map) {
  const zones = useLiveStore((s) => s.zones);
  const upsert = useLiveStore((s) => s.upsert);
  const removeFromStore = useLiveStore((s) => s.remove);
  const [drawing, setDrawing] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const [handle, setHandle] = useState(null);

  // Repaint whenever the zone list changes -- including from another operator's
  // edit arriving over the socket.
  useEffect(() => {
    if (!map) return;
    try {
      renderZones(map, zones);
    } catch {
      /* stub not filled in yet */
    }
  }, [map, zones]);

  const cancelDraw = useCallback(() => {
    handle?.cancel?.();
    setHandle(null);
    setDrawing(false);
  }, [handle]);

  const beginDraw = useCallback(
    (severity) => {
      if (!map) return;
      setError(null);
      try {
        const h = startZoneDraw(map, async (draft) => {
          setDrawing(false);
          setPending(true);
          try {
            upsert("zones", await createZoneRequest({ ...draft, severity }));
          } catch (e) {
            setError(toApiError(e));
          } finally {
            setPending(false);
          }
        });
        setHandle(h);
        setDrawing(true);
      } catch (e) {
        setError({ detail: e.message, code: "not_implemented", status: null, fields: {} });
      }
    },
    [map, upsert]
  );

  const remove = useCallback(
    async (id) => {
      setPending(true);
      try {
        await deleteZoneRequest(id);
        removeFromStore("zones", id);
      } catch (e) {
        setError(toApiError(e));
      } finally {
        setPending(false);
      }
    },
    [removeFromStore]
  );

  return { zones, drawing, pending, error, beginDraw, cancelDraw, remove };
}
