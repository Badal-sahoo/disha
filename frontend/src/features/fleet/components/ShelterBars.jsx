/**
 * capacity fill bars. Amber past 80%, red at full.
 *
 * Fully wired; the thresholds come from fleet.renderShelterBars.
 */
import { useShelterBars } from "../hooks";

export default function ShelterBars() {
  const bars = useShelterBars();

  if (!bars.length) return <p className="empty">No shelters loaded.</p>;

  return (
    <ul className="shelter-bars">
      {bars.map((b) => (
        <li key={b.id} className={`shelter-bars__row is-${b.tone}`}>
          <span className="shelter-bars__name" title={b.code}>{b.name ?? b.code}</span>
          <div className="bar">
            <div className="bar__fill" style={{ width: `${Math.min(b.pct, 100)}%` }} />
          </div>
          <em>{b.label}</em>
        </li>
      ))}
    </ul>
  );
}
