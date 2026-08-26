/**
 * WebSocket transport. Fully implemented -- reconnect, auth and the resync
 * contract are all wiring, not logic.
 *
 * Two channels (system design 07):
 *   /ws/ops           every dashboard joins; receives all ten event types
 *   /ws/unit/{code}   one team, so a crew on a phone is not parsing the
 *                     whole district's traffic
 *
 * The token goes in the QUERY STRING because a browser cannot set an
 * Authorization header on a WebSocket handshake. backend/realtime/middleware.py
 * reads it from there.
 */
import { useAuthStore } from "@/features/auth/store";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws";

/** Custom close codes the backend sends. Anything else is a network drop. */
const CLOSE_UNAUTHENTICATED = 4401; // token missing/expired -> refresh, retry
const CLOSE_FORBIDDEN = 4403; // not your unit -> do not retry

/**
 * Open a resilient connection to one channel.
 *
 * IN : path      = str        "/ops" or "/unit/BOAT-04"
 *      handlers  = {
 *        onEvent:   (event) => void,   // event = {type: str, data: obj}
 *        onOpen:    () => void,        // ALSO fires on every RECONNECT --
 *                                      //   call resyncFullState() from here
 *        onClose:   (code) => void,
 *      }
 * OUT: {close: () => void}   -- call it on unmount, or the socket outlives
 *                               the component and reconnects forever
 *
 * RECONNECT: exponential backoff 1s, 2s, 4s ... capped at 30s, reset to 1s on a
 * successful open. On a 4401 close it asks the auth store for the current
 * access token again before retrying -- by then the axios interceptor will
 * usually have refreshed it.
 */
export function connectChannel(path, { onEvent, onOpen, onClose } = {}) {
  let socket = null;
  let closedByUs = false;
  let retryMs = 1000;
  let timer = null;

  function open() {
    const { access } = useAuthStore.getState();
    if (!access) {
      // Nothing to authenticate with. Try again shortly; a login may be in flight.
      timer = setTimeout(open, retryMs);
      return;
    }

    socket = new WebSocket(`${WS_URL}${path}?token=${encodeURIComponent(access)}`);

    socket.onopen = () => {
      retryMs = 1000;
      onOpen?.();
    };

    socket.onmessage = (raw) => {
      try {
        // IN : raw.data = '{"type": "incident.new", "data": {...}}'
        // OUT: handed to onEvent as a parsed object
        onEvent?.(JSON.parse(raw.data));
      } catch {
        /* a malformed frame must not kill the socket */
      }
    };

    socket.onclose = (e) => {
      onClose?.(e.code);
      if (closedByUs || e.code === CLOSE_FORBIDDEN) return;
      timer = setTimeout(open, retryMs);
      retryMs = Math.min(retryMs * 2, 30000);
    };

    socket.onerror = () => socket?.close();
  }

  open();

  return {
    close() {
      closedByUs = true;
      clearTimeout(timer);
      socket?.close();
    },
  };
}

/**
 * The ops channel. Every dashboard calls this exactly once.
 *
 * IN : handlers = same shape as connectChannel
 * OUT: {close}
 */
export function connectOps(handlers) {
  return connectChannel("/ops", handlers);
}

/**
 * One team's channel.
 *
 * IN : code     = str   Resource.code, "BOAT-04"
 *      handlers = same shape as connectChannel
 * OUT: {close}
 *
 * Closes with 4403 and does NOT retry when the logged-in user does not drive
 * that unit -- retrying a permission failure just hammers the server.
 */
export function connectUnit(code, handlers) {
  return connectChannel(`/unit/${encodeURIComponent(code)}`, handlers);
}

export { CLOSE_UNAUTHENTICATED, CLOSE_FORBIDDEN };
