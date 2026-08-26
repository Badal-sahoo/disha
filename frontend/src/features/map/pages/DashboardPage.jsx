/**
 * The ops room. One screen, nine features.
 *
 * Fully wired: it opens the socket, mounts the map, and lays every panel out.
 * Each panel renders its own feature's stubs, so as the team fills those in the
 * screen comes alive piece by piece with no changes here.
 */
import { useState } from "react";

import AlertConsole from "@/features/alerts/components/AlertConsole";
import DispatchPanel from "@/features/dispatch/components/DispatchPanel";
import KpiStrip from "@/features/dispatch/components/KpiStrip";
import FleetLayer from "@/features/fleet/components/FleetLayer";
import ShelterBars from "@/features/fleet/components/ShelterBars";
import HeatLayer from "@/features/heatmap/components/HeatLayer";
import RosterPanel from "@/features/resources/components/RosterPanel";
import FlowLayer from "@/features/supply/components/FlowLayer";
import Scrubber from "@/features/timeline/components/Scrubber";
import ZoneEditor from "@/features/zones/components/ZoneEditor";
import Layout from "@/shared/components/Layout";
import Panel from "@/shared/components/Panel";

import MapCanvas from "../components/MapCanvas";
import { useOpsSocket } from "../hooks";

export default function DashboardPage() {
  const [map, setMap] = useState(null);
  useOpsSocket(null); // null bbox = the whole district

  return (
    <Layout>
      <KpiStrip />

      <div className="dashboard">
        <aside className="dashboard__left">
          <Panel title="Dispatch" subtitle="F10 - the A/B toggle">
            <DispatchPanel />
          </Panel>
          <Panel title="Roster" subtitle="F11">
            <RosterPanel />
          </Panel>
        </aside>

        <main className="dashboard__map">
          <MapCanvas onMap={setMap} />
          {/* Layer components render nothing; they attach to the map instance. */}
          <HeatLayer map={map} />
          <FleetLayer map={map} />
          <FlowLayer map={map} />
          <ZoneEditor map={map} />
        </main>

        <aside className="dashboard__right">
          <Panel title="Alerts" subtitle="F13 - CAP warnings">
            <AlertConsole map={map} />
          </Panel>
          <Panel title="Shelters" subtitle="F9">
            <ShelterBars />
          </Panel>
        </aside>
      </div>

      <Scrubber />
    </Layout>
  );
}
