/**
 * F10 -- the five numbers across the top. Fully wired.
 *
 * Reads the live store's authoritative kpi, and falls back to the currently
 * previewed policy's kpi so the strip moves the moment the toggle flips.
 */
import { useLiveStore } from "@/shared/store/liveStore";

import { useDispatchStore } from "../store";

/**
 * IN : value = number|null, digits = int
 * OUT: str -- "--" for null/NaN, so an empty database never renders "NaN".
 */
function fmt(value, digits = 1) {
  if (value == null || Number.isNaN(value)) return "--";
  return Number(value).toFixed(digits);
}

export default function KpiStrip() {
  const liveKpi = useLiveStore((s) => s.kpi);
  const connected = useLiveStore((s) => s.connected);
  const policy = useDispatchStore((s) => s.policy);
  const previewKpi = useDispatchStore((s) => s.plans[s.policy]?.kpi);

  const kpi = previewKpi ?? liveKpi ?? {};

  const cells = [
    { label: "Critical mean", value: `${fmt(kpi.crit_mean)} min` },
    { label: "Critical p90", value: `${fmt(kpi.crit_p90)} min` },
    { label: "SLA met", value: `${fmt(kpi.crit_sla_pct, 0)}%` },
    { label: "Unreached", value: kpi.unreached ?? "--" },
    { label: "Awaiting", value: kpi.awaiting ?? "--" },
  ];

  return (
    <div className="kpi-strip">
      {cells.map((c) => (
        <div className="kpi-strip__cell" key={c.label}>
          <span className="kpi-strip__label">{c.label}</span>
          <strong className="kpi-strip__value">{c.value}</strong>
        </div>
      ))}
      <div className="kpi-strip__cell kpi-strip__cell--meta">
        <span className="kpi-strip__label">Policy</span>
        <strong className="kpi-strip__value">{policy}</strong>
      </div>
      <div className={connected ? "kpi-strip__dot is-live" : "kpi-strip__dot"}>
        {connected ? "live" : "offline"}
      </div>
    </div>
  );
}
