/**
 * One card per affected area, not one row per report.
 *
 * Five people reporting the same flood create five Incident rows that share a
 * cell_id. Showing them as five separate jobs makes one flood look like five,
 * so they are grouped back together here.
 *
 * PROPS:
 *   incidents   = [{id, cell_id, severity, people, description, reported_at,
 *                   corroborations, status}]
 *   assignments = the proposed plan
 *   live        = assignments already committed, straight from the live store
 *   onCommit    = (codes) => Promise
 *   onExplain   = (code) => void
 *   busy        = bool
 */
import { useState } from "react";

import { SEVERITY_COLORS, STATUS_COLORS } from "@/shared/utils/constants";
import { ago } from "@/shared/utils/format";

/** A dispatch that is under way: told to a unit, not yet finished. */
const isLive = (a) => a.status !== "PROPOSED" && a.status !== "COMPLETE";

/** Roll incidents up into one entry per cell, worst and oldest first. */
export function groupByArea(incidents, assignments, live = []) {
  const areas = new Map();

  for (const incident of incidents) {
    if (incident.status === "RESOLVED") continue;

    const key = incident.cell_id || `${incident.id}`;
    let area = areas.get(key);
    if (!area) {
      area = {
        key,
        // The first report in the cell names the whole area. "19.93,85.84" is
        // a grid bucket, not something an operator can say out loud on a radio.
        code: incident.code,
        incidents: [],
        people: 0,
        severity: 0,
        oldest: incident.reported_at,
        reporters: incident.corroborations ?? 1,
      };
      areas.set(key, area);
    }

    area.incidents.push(incident);
    // Oldest code wins, so the label does not jump around as reports arrive.
    if (incident.code && incident.code < area.code) area.code = incident.code;
    area.people += incident.people ?? 0;
    area.severity = Math.max(area.severity, incident.severity ?? 0);
    area.reporters = Math.max(area.reporters, incident.corroborations ?? 1);
    if (incident.reported_at < area.oldest) area.oldest = incident.reported_at;
  }

  // Attach both halves of the story: what is PROPOSED for this area, and what
  // has already been sent. Without the second half an area that was just
  // dispatched goes ASSIGNED, drops out of the plan, and the card claims "no
  // unit" for work that is on its way.
  for (const area of areas.values()) {
    const mine = new Set(area.incidents.map((i) => i.id));
    area.assignments = assignments.filter((a) => mine.has(a.incident));
    area.live = live.filter((a) => mine.has(a.incident) && isLive(a));
  }

  return [...areas.values()].sort(
    (a, b) => b.severity - a.severity || a.oldest.localeCompare(b.oldest)
  );
}

export default function TaskCards({ incidents = [], assignments = [], live = [], onCommit,
                                    onExplain, busy = false }) {
  const [openKey, setOpenKey] = useState(null);
  const areas = groupByArea(incidents, assignments, live);

  if (!areas.length) {
    return <p className="empty">Nothing waiting. Every report has been handled.</p>;
  }

  return (
    <ul className="task-cards">
      {areas.map((area) => {
        const open = area.key === openKey;
        const planned = area.assignments;
        const sent = area.live;

        return (
          <li
            key={area.key}
            className={`task-card${open ? " is-open" : ""}${sent.length ? " is-sent" : ""}`}
          >
            <button
              type="button"
              className="task-card__head"
              onClick={() => setOpenKey(open ? null : area.key)}
              aria-expanded={open}
            >
              {/* Severity carries the most weight on this card, so it gets a
                  bar rather than a dot: 8px of colour cannot rank five levels
                  against each other once two cards sit side by side. */}
              <span
                className="sev-bar"
                style={{ background: SEVERITY_COLORS[area.severity] }}
                aria-hidden="true"
              />
              <span className="task-card__where">
                {area.code}
                {area.incidents.length > 1 && (
                  <span className="muted"> +{area.incidents.length - 1}</span>
                )}
              </span>
              {/* "cell 19.93,85.84" was in this line. It is a grid bucket, not
                  somewhere an operator can say out loud on a radio, and it was
                  the widest thing on the card. */}
              <span className="task-card__meta">
                sev {area.severity} · {area.people} people · {area.reporters} reported ·{" "}
                {ago(area.oldest)}
              </span>
              {sent.length ? (
                <span className="pill is-sent">{sent.length} on the way</span>
              ) : (
                <span className={planned.length ? "pill is-live" : "pill"}>
                  {planned.length ? `${planned.length} unit ready` : "no unit"}
                </span>
              )}
            </button>

            {open && (
              <div className="task-card__detail">
                <ul className="task-card__reports">
                  {area.incidents.map((incident) => (
                    <li key={incident.id}>
                      <strong>{incident.code}</strong> · severity {incident.severity} ·{" "}
                      {incident.people} people
                      {incident.description && <div>{incident.description}</div>}
                    </li>
                  ))}
                </ul>

                {sent.length > 0 && (
                  <ul className="task-card__units task-card__units--sent">
                    {sent.map((a) => (
                      <li key={a.code}>
                        <span className="dot" style={{ background: STATUS_COLORS.ENROUTE }} />
                        <strong>{a.resource_code}</strong>
                        <span className="muted">
                          {a.status.toLowerCase().replace("_", " ")}
                          {a.eta_min != null && ` · ${a.eta_min.toFixed(0)} min`}
                          {a.shelter_code && ` → ${a.shelter_code}`}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}

                {planned.length === 0 ? (
                  sent.length === 0 && <p className="empty">No unit can reach this yet.</p>
                ) : (
                  <>
                    <ul className="task-card__units">
                      {planned.map((a) => (
                        <li key={a.code}>
                          <strong>{a.resource_code}</strong> — {a.eta_min?.toFixed(0)} min
                          {a.shelter_code && ` → ${a.shelter_code}`}
                          <button
                            type="button"
                            className="btn--ghost"
                            onClick={() => onExplain?.(a.code)}
                          >
                            Why this unit?
                          </button>
                        </li>
                      ))}
                    </ul>

                    <button
                      type="button"
                      className="btn--commit btn--block"
                      disabled={busy}
                      onClick={() => onCommit?.(planned.map((a) => a.code))}
                    >
                      Dispatch {planned.length > 1 ? `${planned.length} units` : "unit"}
                    </button>
                  </>
                )}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
