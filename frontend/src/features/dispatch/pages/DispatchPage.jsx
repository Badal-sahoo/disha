/**
 * The decision: compare the three strategies, then send units.
 *
 * On its own page because it is the one screen where an operator commits to
 * something irreversible, and it deserves the room to be read carefully.
 */
import Panel from "@/shared/components/Panel";

import DispatchPanel from "../components/DispatchPanel";

export default function DispatchPage() {
  return (
    <div className="page">
      <header className="page__head">
        <h1 className="page__title">Dispatch</h1>
        <p className="page__hint">
          One card per affected area, worst first. Pick a strategy, open a card
          to see which unit it proposes and why, then send it.
        </p>
      </header>

      <div className="page__grid page__grid--wide">
        <Panel title="Areas waiting" subtitle="who goes where, and why">
          <DispatchPanel />
        </Panel>
      </div>
    </div>
  );
}
