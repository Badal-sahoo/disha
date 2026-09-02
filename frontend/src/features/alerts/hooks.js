/**
 * CAP warnings: load them and keep their polygons on the map.
 */
import { useCallback, useEffect, useState } from "react";

import { toApiError } from "@/shared/api/client";
import { useLiveStore } from "@/shared/store/liveStore";

import { fetchAlerts } from "./api";
import { renderCapPolygon } from "./cap";

/** IN: map | null -- OUT: {alerts, pending, error, reload} */
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
    } catch (requestError) {
      setError(toApiError(requestError));
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
    renderCapPolygon(map, alerts);
  }, [map, alerts]);

  return { alerts, pending, error, reload };
}
