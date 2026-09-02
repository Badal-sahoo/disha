/**
 * SMS triage hook.
 *
 * Polls, because an SMS arrives through the phone gateway rather than through
 * the websocket, so there is no delta event to listen for.
 */
import { useCallback, useEffect, useState } from "react";

import { toApiError } from "@/shared/api/client";

import { fetchUnparsedSms } from "./api";

const REFRESH_MS = 20000;

/** OUT: {messages, pending, error, reload} */
export function useSmsTriage() {
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    setPending(true);
    try {
      setMessages(await fetchUnparsedSms());
      setError(null);
    } catch (requestError) {
      setError(toApiError(requestError));
    } finally {
      setPending(false);
    }
  }, []);

  useEffect(() => {
    reload();
    const timer = setInterval(reload, REFRESH_MS);
    return () => clearInterval(timer);
  }, [reload]);

  return { messages, pending, error, reload };
}
