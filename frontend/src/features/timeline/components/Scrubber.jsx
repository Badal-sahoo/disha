/**
 * F15 -- the replay bar along the bottom. Fully wired.
 */
import { useState } from "react";

import { useTimeline } from "../hooks";

/** IN: hoursAgo = int -- OUT: ISO 8601 string */
function isoHoursAgo(hoursAgo) {
  return new Date(Date.now() - hoursAgo * 3600_000).toISOString();
}

export default function Scrubber() {
  const { events, pending, error, load, seek, exportReport } = useTimeline();
  const [from] = useState(() => isoHoursAgo(6));
  const [to] = useState(() => new Date().toISOString());
  const [pos, setPos] = useState(0);

  return (
    <footer className="scrubber">
      <button type="button" onClick={() => load(from, to)} disabled={pending}>
        Load last 6h
      </button>

      <input
        type="range"
        min={0}
        max={Math.max(events.length - 1, 0)}
        value={pos}
        disabled={!events.length}
        onChange={(e) => {
          const i = Number(e.target.value);
          setPos(i);
          if (events[i]) seek(events[i].t);
        }}
      />

      <span className="muted">
        {events.length ? `${pos + 1} / ${events.length}` : "no events loaded"}
      </span>

      <button type="button" onClick={() => exportReport(from, to, "csv")} disabled={pending}>
        Export after-action
      </button>

      {error && <span className="error">{error.detail}</span>}
    </footer>
  );
}
