/**
 * F14 -- supply flows on the map, plus the commit button.
 *
 * PROPS: map = maplibregl.Map | null
 */
import { useState } from "react";

import { useSupplyPlan } from "../hooks";

export default function FlowLayer({ map }) {
  const { flows, pending, error, commit } = useSupplyPlan(map);
  const [result, setResult] = useState(null);

  // Nothing to show yet -- stay out of the operator's way rather than render an
  // empty box over the map.
  if (error || !flows.length) return null;

  return (
    <div className="flow-layer">
      <span>
        {flows.length} supply flows,{" "}
        {flows.reduce((sum, f) => sum + (f.quantity ?? 0), 0)} units
      </span>
      <button type="button" disabled={pending} onClick={() => commit().then(setResult)}>
        Commit supply plan
      </button>
      {result && <em className="muted">{result.committed} committed</em>}
    </div>
  );
}
