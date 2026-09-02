/**
 * Fully implemented -- reads come from the live store (already
 * pushed there by the socket), writes go straight to the API and the resulting
 * broadcast updates every dashboard.
 */
import { useCallback, useMemo, useState } from "react";

import { toApiError } from "@/shared/api/client";
import { useLiveStore } from "@/shared/store/liveStore";

import {
  adjustOccupancy as adjustOccupancyRequest,
  setShelterStatus as setShelterStatusRequest,
  updateResourceStatus as updateResourceStatusRequest,
} from "./api";

/**
 * The roster panel.
 *
 * IN : filter = {status?: str, kind?: str}
 * OUT: {
 *        resources: [resource, ...],   // filtered, from the live store
 *        pending:   bool,
 *        error:     obj|null,
 *        setStatus: (code, status) => Promise<resource>,
 *      }
 *
 * Reads the store rather than re-fetching: the socket already keeps it current,
 * and a second fetch would race the deltas.
 */
export function useResources(filter = {}) {
  const all = useLiveStore((s) => s.resources);
  const upsert = useLiveStore((s) => s.upsert);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const resources = useMemo(
    () =>
      all.filter(
        (r) =>
          (!filter.status || r.status === filter.status) && (!filter.kind || r.kind === filter.kind)
      ),
    [all, filter.status, filter.kind]
  );

  const setStatus = useCallback(
    async (code, status) => {
      setPending(true);
      setError(null);
      try {
        const updated = await updateResourceStatusRequest(code, status);
        upsert("resources", updated); // optimistic; the broadcast confirms it
        return updated;
      } catch (e) {
        setError(toApiError(e));
        throw e;
      } finally {
        setPending(false);
      }
    },
    [upsert]
  );

  return { resources, pending, error, setStatus };
}

/**
 * The shelter panel.
 *
 * IN : --
 * OUT: {
 *        shelters:  [shelter, ...],
 *        pending:   bool,
 *        error:     obj|null,
 *        setStatus: (code, status) => Promise<shelter>,
 *        adjust:    (code, delta)  => Promise<shelter>,
 *      }
 */
export function useShelters() {
  const shelters = useLiveStore((s) => s.shelters);
  const upsert = useLiveStore((s) => s.upsert);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback(
    async (fn) => {
      setPending(true);
      setError(null);
      try {
        const updated = await fn();
        upsert("shelters", updated);
        return updated;
      } catch (e) {
        setError(toApiError(e));
        throw e;
      } finally {
        setPending(false);
      }
    },
    [upsert]
  );

  return {
    shelters,
    pending,
    error,
    setStatus: (code, status) => run(() => setShelterStatusRequest(code, status)),
    adjust: (code, delta) => run(() => adjustOccupancyRequest(code, delta)),
  };
}
