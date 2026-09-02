/**
 * The no-internet path's human-in-the-loop.
 *
 * A text we could not place is deliberately NOT put on the map -- guessing a
 * location would send a boat to the wrong village. It waits here with its raw
 * wording, so an operator who recognises the landmark can act on it.
 */
import { ago } from "@/shared/utils/format";

import { useSmsTriage } from "../hooks";

export default function SmsTriage() {
  const { messages, pending, error, reload } = useSmsTriage();

  if (error) return <p className="error">{error.detail}</p>;

  if (!messages.length) {
    return <p className="empty">{pending ? "Checking…" : "Nothing waiting. Every text was placed."}</p>;
  }

  return (
    <>
      <button type="button" className="btn--ghost" onClick={reload} disabled={pending}>
        {pending ? "Checking…" : "Refresh"}
      </button>

      <ul className="sms-triage">
        {messages.map((message) => (
          <li key={message.id} className="sms-triage__row">
            <div className="sms-triage__body">{message.body}</div>
            <div className="sms-triage__meta">
              {message.from_number} · {ago(message.received_at)} ·{" "}
              {message.incident
                ? `on the map, low confidence (${message.confidence.toFixed(1)})`
                : "no location found"}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
