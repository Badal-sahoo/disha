/**
 * F13 hooks. Fully wired -- fetch, preposition and broadcast all round-trip.
 * The polygon rendering is the stub in cap.js.
 */
import { useCallback, useEffect, useState } from "react";

import { toApiError } from "@/shared/api/client";
import { useLiveStore } from "@/shared/store/liveStore";

import {
  broadcastCitizenAlert as broadcastRequest,
  fetchAlerts,
  prePosition as prePositionRequest,
} from "./api";
import { renderCapPolygon } from "./cap";

/**
 * IN : map = maplibregl.Map | null
 * OUT: {
 *        alerts:      [alert, ...],
 *        pending:     bool,
 *        error:       obj|null,
 *        reload:      () => Promise<void>,
 *        preposition: (id, maxUnits) => Promise<[assignment]>,
 *        broadcast:   (id, text, channels) => Promise<{queued, devices, numbers}>,
 *      }
 */
export function useAlerts(map) {
  const alerts = useLiveStore((s) => s.alerts);
  const patch = useLiveStore((s) => s.patch);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    setPending(true);
    setError(null);
    try {
      patch({ alerts: await fetchAlerts(true) });
    } catch (e) {
      setError(toApiError(e));
    } finally {
      setPending(false);
    }
  }, [patch]);

  // The socket delivers alert.new, but a dashboard opened after a warning
  // arrived has to fetch the backlog once.
  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    if (!map) return;
    try {
      renderCapPolygon(map, alerts);
    } catch {
      /* stub not filled in yet */
    }
  }, [map, alerts]);

  const preposition = useCallback(async (id, maxUnits = 5) => {
    setPending(true);
    try {
      return await prePositionRequest(id, maxUnits);
    } catch (e) {
      setError(toApiError(e));
      throw e;
    } finally {
      setPending(false);
    }
  }, []);

  const broadcast = useCallback(async (id, text, channels) => {
    setPending(true);
    try {
      return await broadcastRequest(id, text, channels);
    } catch (e) {
      setError(toApiError(e));
      throw e;
    } finally {
      setPending(false);
    }
  }, []);

  return { alerts, pending, error, reload, preposition, broadcast };
}
