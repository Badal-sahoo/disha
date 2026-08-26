/**
 * F10 -- the proposed dispatches, with per-row commit. Fully wired.
 *
 * PROPS:
 *   assignments = [{code, incident_code, resource_code, shelter_code, eta_min,
 *                   gain, status}]
 *   onCommit    = (codes: [str]) => Promise
 *   onExplain   = (code: str) => void
 *   busy        = bool
 */
export default function PlanTable({ assignments = [], onCommit, onExplain, busy = false }) {
  if (!assignments.length) {
    return <p className="muted">No dispatches proposed. Every open incident is covered.</p>;
  }

  return (
    <table className="plan-table">
      <thead>
        <tr>
          <th>Unit</th>
          <th>Incident</th>
          <th>Shelter</th>
          <th>ETA</th>
          <th>Gain</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {assignments.map((a) => (
          <tr key={a.code}>
            <td>{a.resource_code}</td>
            <td>{a.incident_code}</td>
            <td>{a.shelter_code ?? "--"}</td>
            <td>{a.eta_min?.toFixed(1)} min</td>
            <td>{a.gain?.toFixed(2)}</td>
            <td className="plan-table__actions">
              <button type="button" onClick={() => onExplain?.(a.code)}>
                Why?
              </button>
              <button type="button" onClick={() => onCommit?.([a.code])} disabled={busy}>
                Dispatch
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
