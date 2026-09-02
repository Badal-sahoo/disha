/**
 * What the district is telling us: citizen reports, official warnings, and the
 * texts we could not place on the map.
 *
 * All three are inbound and none is a decision, which is why they share a page.
 */
import SmsTriage from "@/features/ingest/components/SmsTriage";
import Panel from "@/shared/components/Panel";
import { useLiveStore } from "@/shared/store/liveStore";
import { SEVERITY_COLORS } from "@/shared/utils/constants";
import { ago } from "@/shared/utils/format";

import AlertConsole from "../components/AlertConsole";

/**
 * Every report that has arrived, newest first.
 *
 * This panel exists because a report that WORKS used to vanish from this page:
 * once it is placed it becomes an incident, and incidents were only visible on
 * the map and in Dispatch. So the one section named "Incoming" showed
 * everything except the thing actually coming in.
 *
 * Reads straight from the live store, so a report sent from the phone appears
 * here the moment the socket delivers it -- no refresh.
 */
function ReportFeed() {
  const incidents = useLiveStore((s) => s.incidents);

  if (!incidents.length) {
    return <p className="empty">No reports yet. The district is quiet.</p>;
  }

  // reported_at is ISO 8601, so a plain string compare sorts it correctly.
  const newest = [...incidents]
    .sort((a, b) => (a.reported_at < b.reported_at ? 1 : -1))
    .slice(0, 12);

  return (
    <ul className="report-feed">
      {newest.map((incident) => (
        <li key={incident.id} className="report-feed__row">
          <span
            className="dot"
            style={{ background: SEVERITY_COLORS[incident.severity] }}
          />
          <span className="report-feed__code">{incident.code}</span>
          <span className="report-feed__what">
            {incident.kind?.toLowerCase()} · severity {incident.severity} ·{" "}
            {incident.people} {incident.people === 1 ? "person" : "people"}
          </span>
          <span className="report-feed__when">{ago(incident.reported_at)}</span>
          <span className={incident.status === "OPEN" ? "pill" : "pill is-sent"}>
            {incident.status === "OPEN" ? "waiting" : "unit sent"}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function IncomingPage() {
  const total = useLiveStore((s) => s.incidents.length);

  return (
    <div className="page">
      <header className="page__head">
        <h1 className="page__title">Incoming</h1>
        <p className="page__hint">
          Everything arriving from the district: reports from the app and by SMS,
          the government warning feed, and messages that arrived without a usable
          location.
        </p>
      </header>

      <div className="page__grid">
        <Panel title="Citizen reports" subtitle={`${total} received`}>
          <ReportFeed />
        </Panel>

        <Panel title="Warnings" subtitle="government CAP feed">
          {/* No map on this page -- the polygons are drawn by AlertLayer on the
              Live map section instead. */}
          <AlertConsole map={null} />
        </Panel>

        <Panel title="Could not place" subtitle="texts waiting for a human">
          <SmsTriage />
        </Panel>
      </div>
    </div>
  );
}
