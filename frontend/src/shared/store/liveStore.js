/**
 * F7 -- the ONE in-memory store. Every dashboard feature reads from here rather
 * than fetching its own copy, which is what keeps the map, the KPI strip and
 * the panels from disagreeing with each other.
 *
 * The setters below are implemented (plumbing). applyDelta -- the reducer that
 * patches this store from a socket event -- lives in features/map/map.js and is
 * a stub, because how each event merges is real logic.
 */
import { create } from "zustand";

/**
 * The shape every feature reads. Same keys as GET /api/state, so a full sync
 * and a delta patch land in exactly the same place.
 */
const EMPTY = {
  t: null, //  ISO 8601 of the last applied event or full sync
  incidents: [], //  {id, code, lat, lon, kind, severity, people, cell_id,
  //                  corroborations, status, reported_at, first_response_at}
  resources: [], //  {id, code, name, kind, lat, lon, capabilities[], capacity,
  //                  speed_kmph, status, free_at, base_name}
  shelters: [], //   {id, code, name, lat, lon, capacity, occupancy, remaining, status}
  zones: [], //      {id, lat, lon, radius_km, severity, source, active, created_at}
  assignments: [], //{id, code, incident, incident_code, incident_lat, incident_lon,
  //                  resource, resource_code, resource_lat, resource_lon,
  //                  shelter, shelter_code, eta_min, gain, policy, status,
  //                  rescued_count, dispatched_at, arrived_at, completed_at}
  alerts: [], //     {id, identifier, event, severity, urgency, certainty,
  //                  polygon[[lat,lon]], sent_at, expires_at, active}
  kpi: null, //      {crit_mean, crit_p90, crit_sla_pct, unreached, awaiting}

  connected: false, // socket state, for the header indicator
  lastSyncAt: null, // ISO 8601 of the last resyncFullState()
};

export const useLiveStore = create((set, get) => ({
  ...EMPTY,

  /**
   * Replace everything from a full snapshot. Called on page load AND after
   * every socket reconnect -- deltas missed while disconnected are gone
   * forever, so this is the reconciliation path that makes the stream safe.
   *
   * IN : state = the GET /api/state body
   *      {t, incidents[], resources[], shelters[], zones[], assignments[],
   *       alerts[], kpi{}}
   * OUT: void
   */
  hydrate: (state) =>
    set({
      t: state.t ?? null,
      incidents: state.incidents ?? [],
      resources: state.resources ?? [],
      shelters: state.shelters ?? [],
      zones: state.zones ?? [],
      assignments: state.assignments ?? [],
      alerts: state.alerts ?? [],
      kpi: state.kpi ?? null,
      lastSyncAt: new Date().toISOString(),
    }),

  /**
   * Shallow-merge a patch. applyDelta() builds the patch; this applies it.
   *
   * IN : patch = a partial of the shape above, e.g. {incidents: [...]}
   * OUT: void
   */
  patch: (patch) => set(patch),

  /**
   * Insert-or-replace one row inside a collection, matched on `id`.
   *
   * IN : collection = str   "incidents"|"resources"|"shelters"|"zones"
   *                         |"assignments"|"alerts"
   *      row        = obj   must carry an `id`
   * OUT: void
   */
  upsert: (collection, row) =>
    set((s) => {
      const list = s[collection] ?? [];
      const i = list.findIndex((x) => x.id === row.id);
      if (i === -1) return { [collection]: [row, ...list] };
      const next = list.slice();
      next[i] = { ...next[i], ...row };
      return { [collection]: next };
    }),

  /**
   * Drop one row from a collection.
   *
   * IN : collection = str, id = int
   * OUT: void
   */
  remove: (collection, id) =>
    set((s) => ({ [collection]: (s[collection] ?? []).filter((x) => x.id !== id) })),

  /** IN: connected = bool -- OUT: void. Drives the header indicator. */
  setConnected: (connected) => set({ connected }),

  /** Wipe on logout, so the next user does not see the last one's district. */
  reset: () => set({ ...EMPTY }),

  // --- selectors: derived reads, so components never re-filter in render ---

  /** OUT: [incident, ...] with status "OPEN" */
  openIncidents: () => get().incidents.filter((i) => i.status === "OPEN"),

  /** OUT: [resource, ...] with status "IDLE" -- what the next solve can use */
  idleResources: () => get().resources.filter((r) => r.status === "IDLE"),

  /** OUT: [assignment, ...] that are live (not PROPOSED, not COMPLETE) */
  activeAssignments: () =>
    get().assignments.filter((a) => a.status !== "PROPOSED" && a.status !== "COMPLETE"),

  /**
   * IN : id = int
   * OUT: incident|undefined
   */
  incidentById: (id) => get().incidents.find((i) => i.id === id),
}));
