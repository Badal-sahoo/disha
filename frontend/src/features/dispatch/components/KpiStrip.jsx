/**
 * Response summary: the four numbers across the top.
 *
 * MEASURED ONLY. These are what the district has actually achieved -- never a
 * prediction. An earlier version swapped in the pending plan's forecast and
 * tinted the band to say so; it was still read as the real thing, and an
 * operator looking at a freshly seeded district saw a full set of response
 * times for work nobody had done yet. If a figure is here, it happened.
 *
 * Every figure also carries its state. Rendered in one colour, "Reached in
 * time: 62%" and "98%" look identical, and the band that exists to give an
 * operator situational awareness cannot tell a quiet afternoon from a disaster.
 */
import { HORIZON_MIN } from "@/shared/utils/constants";

import { useLiveStore } from "@/shared/store/liveStore";

/**
 * IN : value = number|null, digits = int
 * OUT: str -- "--" for null/NaN, so an empty database never renders "NaN".
 */
function fmt(value, digits = 1) {
  if (value == null || Number.isNaN(value)) return "--";
  return Number(value).toFixed(digits);
}

/**
 * Which way is good.
 *
 * The response thresholds are read off the solver's own horizon rather than
 * invented here: the engine costs an assignment as w * (eta - HORIZON_MIN), so
 * a quarter of the horizon is comfortably inside it and half of it is not.
 *
 * IN : value = number|null, good = number, warn = number, lowerIsBetter = bool
 * OUT: "" | " is-good" | " is-warn" | " is-bad"
 */
function tone(value, good, warn, lowerIsBetter = true) {
  if (value == null || Number.isNaN(value)) return "";
  const v = Number(value);
  const ok = lowerIsBetter ? v <= good : v >= good;
  const mid = lowerIsBetter ? v <= warn : v >= warn;
  if (ok) return " is-good";
  if (mid) return " is-warn";
  return " is-bad";
}

export default function KpiStrip() {
  const kpi = useLiveStore((s) => s.kpi) ?? {};

  const cells = [
    {
      label: "Avg response",
      value: kpi.crit_mean == null ? "--" : `${fmt(kpi.crit_mean)} min`,
      tone: tone(kpi.crit_mean, HORIZON_MIN * 0.25, HORIZON_MIN * 0.5),
      hint: "serious calls",
    },
    {
      label: "Reached in time",
      // "--%" reads as a broken template; a missing measurement is just "--".
      value: kpi.crit_sla_pct == null ? "--" : `${fmt(kpi.crit_sla_pct, 0)}%`,
      tone: tone(kpi.crit_sla_pct, 90, 70, false),
      hint: "serious calls inside the horizon",
    },
    {
      label: "No unit assigned",
      value: kpi.unreached ?? "--",
      tone: tone(kpi.unreached, 0, 2),
    },
    {
      label: "Waiting",
      value: kpi.awaiting ?? "--",
      tone: tone(kpi.awaiting, 0, 5),
    },
  ];

  return (
    <div className="kpi-strip">
      {cells.map((c) => (
        <div className="kpi-strip__cell" key={c.label}>
          <span className="label" title={c.hint}>
            {c.label}
          </span>
          <strong className={`kpi-strip__value${c.tone}`}>{c.value}</strong>
        </div>
      ))}
    </div>
  );
}
