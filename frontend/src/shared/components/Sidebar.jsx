/**
 * The section rail.
 *
 * Each item carries a live count, because a nav item in an ops room should say
 * how much work is behind it, not just where it goes. The counts are three
 * different things on purpose -- warnings, areas waiting, units free -- so each
 * one is labelled rather than left as a bare number.
 *
 * This replaces the numbered "1 / 2 / 3" stage headings. Those implied a
 * sequence the job does not actually have: warnings keep arriving while you are
 * still dispatching the last lot.
 */
import { NavLink } from "react-router-dom";

import { useAuth } from "@/features/auth/hooks";
import { useLiveStore } from "@/shared/store/liveStore";

import ThemeToggle from "./ThemeToggle";

export default function Sidebar() {
  const { user, signOut } = useAuth();

  const warnings = useLiveStore((s) => s.alerts.length);
  // Counted as SCENES, the same way the dispatch cards and the KPI strip count
  // them. Counting raw rows made the badge say 18 while the page it links to
  // showed 10 cards -- five neighbours reporting one flood is one area waiting.
  const waiting = useLiveStore(
    (s) =>
      new Set(
        s.incidents
          .filter((i) => i.status === "OPEN")
          .map((i) => `${i.cell_id}|${i.kind}`)
      ).size
  );
  const free = useLiveStore((s) => s.resources.filter((r) => r.status === "IDLE").length);

  const items = [
    { to: "/", end: true, label: "Live map", note: "the district right now" },
    { to: "/incoming", label: "Incoming", note: "warnings and texts",
      count: warnings, unit: "active warnings" },
    { to: "/dispatch", label: "Dispatch", note: "who goes where",
      count: waiting, unit: "areas waiting" },
    { to: "/resources", label: "Resources", note: "units and shelters",
      count: free, unit: "units free" },
  ];

  return (
    <nav className="sidebar" aria-label="Sections">
      <div className="sidebar__brand">
        <span className="sidebar__mark">DISHA</span>
        <span className="sidebar__sub label">District emergency operations</span>
      </div>

      <ul className="nav">
        {items.map((item) => (
          <li key={item.to}>
            {/* A plain string className would REPLACE NavLink's default and
                drop the active class entirely -- it has to be a function. */}
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav__item${isActive ? " active" : ""}`}
            >
              <span className="nav__label">{item.label}</span>
              <span className="nav__note">{item.note}</span>
              {item.count != null && (
                <span
                  /* A section with nothing waiting must not look like one with
                     work in it -- a bold 0 pulls the eye for no reason. */
                  className={`nav__count${item.count === 0 ? " is-zero" : ""}`}
                  title={`${item.count} ${item.unit}`}
                >
                  {item.count}
                  <span className="sr-only"> {item.unit}</span>
                </span>
              )}
            </NavLink>
          </li>
        ))}
      </ul>

      <div className="sidebar__foot">
        <div className="sidebar__who">
          <strong>{user?.username}</strong>
          <span className="label">{user?.role}</span>
        </div>
        <div className="sidebar__actions">
          <ThemeToggle />
          <button type="button" onClick={signOut}>
            Sign out
          </button>
        </div>
      </div>
    </nav>
  );
}
