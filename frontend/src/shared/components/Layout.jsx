/**
 * The chrome around every authenticated screen.
 *
 * Mounted ONCE, as the parent route, with each page rendering into <Outlet />.
 * That placement is load-bearing: useOpsSocket lives here, so navigating between
 * sections no longer tears the socket down and re-syncs the whole district.
 */
import { Outlet } from "react-router-dom";

import KpiStrip from "@/features/dispatch/components/KpiStrip";
import { useOpsSocket } from "@/features/map/hooks";
import { useLiveStore } from "@/shared/store/liveStore";
import { clock } from "@/shared/utils/format";

import Sidebar from "./Sidebar";

export default function Layout() {
  useOpsSocket(null); // null bbox = the whole district

  const connected = useLiveStore((s) => s.connected);
  const lastSyncAt = useLiveStore((s) => s.lastSyncAt);

  return (
    <div className="layout">
      <Sidebar />

      <div className="layout__main">
        <header className="layout__bar">
          {/* The pulsing dot is the only thing on an idle screen that says the
              socket is still alive. A static label cannot tell you that. */}
          <span className={connected ? "live-dot is-live" : "live-dot"} aria-hidden="true" />
          <span className="label">{connected ? "Live" : "Reconnecting"}</span>

          <span className="layout__spacer" />

          {lastSyncAt && (
            <span className="label">
              Synced <span className="figure">{clock(lastSyncAt)}</span>
            </span>
          )}
        </header>

        <KpiStrip />

        <div className="layout__body">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
