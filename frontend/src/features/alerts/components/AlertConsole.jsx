/**
 * F13 -- IMD and NDMA warnings, and the one action that makes them matter.
 * Fully wired.
 *
 * PROPS: map = maplibregl.Map | null
 */
import { useState } from "react";

import { CAP_SEVERITY_COLORS } from "@/shared/utils/constants";

import { useAlerts } from "../hooks";

export default function AlertConsole({ map }) {
  const { alerts, pending, error, preposition, broadcast } = useAlerts(map);
  const [text, setText] = useState("Cyclone warning. Move to the nearest shelter now.");
  const [result, setResult] = useState(null);

  if (error) return <p className="error">{error.detail}</p>;
  if (!alerts.length) return <p className="muted">No active warnings.</p>;

  return (
    <div className="alert-console">
      <ul className="alert-console__list">
        {alerts.map((a) => (
          <li key={a.id}>
            <header>
              <span className="dot" style={{ background: CAP_SEVERITY_COLORS[a.severity] }} />
              <strong>{a.event}</strong>
              <em className="muted">{a.severity}</em>
            </header>

            <div className="alert-console__actions">
              <button
                type="button"
                disabled={pending}
                onClick={() => preposition(a.id, 5).then((m) => setResult(`${m.length} staged`))}
              >
                Pre-position
              </button>
              <button
                type="button"
                disabled={pending}
                onClick={() =>
                  broadcast(a.id, text, ["PUSH", "SMS"]).then((r) =>
                    setResult(`${r.queued} queued to ${r.devices} devices, ${r.numbers} numbers`)
                  )
                }
              >
                Warn citizens
              </button>
            </div>
          </li>
        ))}
      </ul>

      <textarea
        className="alert-console__text"
        value={text}
        maxLength={160}
        onChange={(e) => setText(e.target.value)}
      />
      {result && <p className="muted">{result}</p>}
    </div>
  );
}
