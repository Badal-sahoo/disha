/**
 * What we have to work with: the unit roster, and how full the shelters are.
 *
 * These two answer the same question from opposite ends -- who can go, and
 * where can they take people -- so they sit side by side.
 */
import ShelterBars from "@/features/fleet/components/ShelterBars";
import Panel from "@/shared/components/Panel";

import RosterPanel from "../components/RosterPanel";

export default function ResourcesPage() {
  return (
    <div className="page">
      <header className="page__head">
        <h1 className="page__title">Resources</h1>
        <p className="page__hint">
          Every unit and its current state, and how much room is left in each
          shelter. Set a unit out of service here and the next plan works around it.
        </p>
      </header>

      <div className="page__grid">
        <Panel title="Rescue units" subtitle="status is editable">
          <RosterPanel />
        </Panel>

        <Panel title="Shelters" subtitle="amber past 80%, red when full">
          <ShelterBars />
        </Panel>
      </div>
    </div>
  );
}
