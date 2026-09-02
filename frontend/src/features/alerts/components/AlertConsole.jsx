/**
 * Government warnings that came in from the CAP feed. The impact area is drawn
 * on the map as a dashed polygon.
 *
 * PROPS: map = maplibregl.Map | null
 */
import { CAP_SEVERITY_COLORS } from "@/shared/utils/constants";
import { stamp } from "@/shared/utils/format";

import { useAlerts } from "../hooks";

export default function AlertConsole({ map }) {
  const { alerts, pending, error } = useAlerts(map);

  if (error) return <p className="error">{error.detail}</p>;
  if (!alerts.length) {
    return <p className="empty">{pending ? "Checking…" : "No active warnings."}</p>;
  }

  return (
    <ul className="alert-console__list">
      {alerts.map((alert) => (
        <li
          key={alert.id}
          /* The severity rides the left edge of the whole row instead of a
             4px dot, so a screen of warnings can be ranked without reading. */
          style={{ borderLeftColor: CAP_SEVERITY_COLORS[alert.severity] }}
        >
          <header>
            <strong>{alert.event}</strong>
            <em style={{ color: CAP_SEVERITY_COLORS[alert.severity] }}>{alert.severity}</em>
          </header>
          <div className="alert-console__when">
            {stamp(alert.sent_at)}
            {alert.expires_at && ` — until ${stamp(alert.expires_at)}`}
          </div>
        </li>
      ))}
    </ul>
  );
}
