/**
 * F14 hooks. Fully wired -- plan and commit round-trip; the arrow geometry is
 * the stub in flows.js.
 */
import { useCallback, useEffect, useState } from "react";

import { toApiError } from "@/shared/api/client";
import { useLiveStore } from "@/shared/store/liveStore";

import { commitSupplyPlan as commitRequest, computeSupplyPlan, fetchStock } from "./api";
import { renderFlows } from "./flows";

/**
 * IN : map = maplibregl.Map | null
 * OUT: {
 *        flows:   [{depot, shelter, item, quantity, cost}],
 *        stock:   [{id, depot, depot_code, item, quantity}],
 *        pending: bool,
 *        error:   obj|null,
 *        reload:  () => Promise<void>,
 *        commit:  () => Promise<{committed, rejected}>,
 *      }
 */
export function useSupplyPlan(map) {
  const shelters = useLiveStore((s) => s.shelters);
  const [flows, setFlows] = useState([]);
  const [stock, setStock] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    setPending(true);
    setError(null);
    try {
      const [plan, stockRows] = await Promise.all([computeSupplyPlan(), fetchStock()]);
      setFlows(plan);
      setStock(stockRows);
    } catch (e) {
      setError(toApiError(e));
    } finally {
      setPending(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    if (!map || !flows.length) return;
    try {
      // Depot coordinates ride along on the stock rows; if your serializer
      // stops including them, add a GET /api/depots rather than guessing.
      const depots = stock.map((s) => ({ code: s.depot_code, lat: s.lat, lon: s.lon }));
      renderFlows(map, flows, depots, shelters);
    } catch {
      /* stub not filled in yet */
    }
  }, [map, flows, stock, shelters]);

  const commit = useCallback(async () => {
    setPending(true);
    try {
      const result = await commitRequest(flows);
      await reload();
      return result;
    } catch (e) {
      setError(toApiError(e));
      throw e;
    } finally {
      setPending(false);
    }
  }, [flows, reload]);

  return { flows, stock, pending, error, reload, commit };
}
