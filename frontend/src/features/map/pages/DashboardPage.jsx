/**
 * The live map: the shared picture every other section talks about.
 *
 * The map owns the whole page. Its two tools -- the layer switch and the zone
 * editor -- float over it, because both only mean anything with the map in
 * front of you. Everything that can be read as a list moved to its own section.
 */
import { useState } from "react";

import FleetLayer from "@/features/fleet/components/FleetLayer";
import ZoneEditor from "@/features/zones/components/ZoneEditor";

import MapCanvas from "../components/MapCanvas";
import MapLayers from "../components/MapLayers";

export default function DashboardPage() {
  const [map, setMap] = useState(null);

  return (
    <div className="map-page">
      <MapCanvas onMap={setMap} />

      {/* Invisible: keeps the unit and route layers in step with the live store.
          The heatmap and the CAP polygon used to be drawn here too. Both are
          gone: the heat showed the last hour and went blank on a quiet
          district, and the warning polygon showed one event. Neither says which
          parts of the district FLOOD, which is what the risk bands in risk.js
          now show and what an operator actually plans around. The CAP feed
          itself still arrives and is listed on Incoming. */}
      <FleetLayer map={map} />

      <MapLayers map={map} />
      <ZoneEditor map={map} />
    </div>
  );
}
