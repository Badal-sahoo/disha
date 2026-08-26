/**
 * F15 hooks. Fetch and export are wired; the fold and the playback clock are
 * the stubs in replay.js.
 */
import { useCallback, useState } from "react";

import { toApiError } from "@/shared/api/client";

import { exportAfterAction, fetchTimeline, saveBlob } from "./api";
import { seekTo } from "./replay";

/**
 * IN : --
 * OUT: {
 *        events:   [{t, type, data}],
 *        snapshot: state|null,     // the folded state at the scrub position
 *        pending:  bool,
 *        error:    obj|null,
 *        load:     (from, to) => Promise<void>,
 *        seek:     (t) => void,
 *        exportReport: (from, to, format) => Promise<void>,  // downloads the file
 *      }
 */
export function useTimeline() {
  const [events, setEvents] = useState([]);
  const [snapshot, setSnapshot] = useState(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async (from, to) => {
    setPending(true);
    setError(null);
    try {
      setEvents(await fetchTimeline(from, to));
    } catch (e) {
      setError(toApiError(e));
    } finally {
      setPending(false);
    }
  }, []);

  const seek = useCallback(
    (t) => {
      try {
        setSnapshot(seekTo(events, t));
      } catch {
        /* stub not filled in yet */
      }
    },
    [events]
  );

  const exportReport = useCallback(async (from, to, format = "csv") => {
    setPending(true);
    try {
      const blob = await exportAfterAction(from, to, format);
      saveBlob(blob, `ps05-after-action.${format}`);
    } catch (e) {
      setError(toApiError(e));
    } finally {
      setPending(false);
    }
  }, []);

  return { events, snapshot, pending, error, load, seek, exportReport };
}
