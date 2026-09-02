/**
 * WebSocket transport for the live map. One channel, no auth -- the socket is
 * read-only and every write still goes through the authenticated REST API.
 */
const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws";

/**
 * Open a self-healing connection to /ws/ops.
 *
 * IN : handlers = {
 *        onEvent: (event) => void,   // event = {type, data}
 *        onOpen:  () => void,        // ALSO fires on every reconnect --
 *                                    //   call resyncFullState() from here
 *        onClose: () => void,
 *      }
 * OUT: {close: () => void}   -- call it on unmount, or the socket outlives the
 *                               component and reconnects forever
 *
 * Reconnect backoff: 1s, 2s, 4s ... capped at 30s, reset on a successful open.
 */
export function connectOps({ onEvent, onOpen, onClose } = {}) {
  let socket = null;
  let closedByUs = false;
  let retryMs = 1000;
  let timer = null;

  function open() {
    socket = new WebSocket(`${WS_URL}/ops`);

    socket.onopen = () => {
      retryMs = 1000;
      onOpen?.();
    };

    socket.onmessage = (raw) => {
      try {
        onEvent?.(JSON.parse(raw.data));
      } catch {
        /* a malformed frame must not kill the socket */
      }
    };

    socket.onclose = () => {
      onClose?.();
      if (closedByUs) return;
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
