/**
 * F15 -- scrub back through the response and replay it. What a real district
 * authority files afterwards, and the answer to "why did it send that unit
 * there?"
 *
 * Owner: Track 2 + Track 5 - Day 6
 */

export function seekTo(events, t) {
  // F15 - Fold every event up to time t into a state snapshot.
  //
  // IN : events = [{t: str, type: str, data: obj}]  ascending, from fetchTimeline
  //      t      = str   ISO 8601 -- the scrub position
  //
  // OUT: {
  //        t:           str,
  //        incidents:   [{id, code, lat, lon, kind, severity, people, cell_id,
  //                       corroborations, status, reported_at}],
  //        resources:   [{id, code, name, kind, lat, lon, status, free_at}],
  //        shelters:    [{id, code, lat, lon, capacity, occupancy, remaining, status}],
  //        zones:       [{id, lat, lon, radius_km, severity, active}],
  //        assignments: [{id, code, incident, resource, eta_min, gain, policy, status}],
  //        alerts:      [{id, identifier, event, severity, polygon}],
  //        kpi:         {crit_mean, crit_p90, crit_sla_pct, unreached, awaiting},
  //      }
  //
  // USE THE SAME REDUCER as the live dashboard: import applyDelta from
  // "@/features/map/map" and fold events into a fresh empty state from zero.
  // Writing a second reducer here means the replay and the live view can
  // disagree -- and the replay is exactly where a judge looks closely.
  //
  // Replay from zero each time rather than stepping backwards. Six hours of
  // events is a few thousand objects; a full refold is instant and cannot
  // accumulate drift.
  throw new Error("TODO seekTo -- Track 2 - Day 6");
}

export function play(events, speed, onFrame) {
  // F15 - Replay at 10x or 60x. Sixty seconds of screen time covers six hours
  //       of operations.
  //
  // IN : events  = [{t, type, data}]
  //      speed   = int              10 | 60
  //      onFrame = (state, t) => void
  // OUT: {pause: () => void, resume: () => void, stop: () => void}
  //
  // Drive it off wall-clock elapsed * speed mapped onto the event timestamps --
  // NOT setInterval over the event array. Events are unevenly spaced: a fixed
  // interval makes a quiet hour take as long as the busy minute that matters.
  throw new Error("TODO play -- Track 2 - Day 6");
}

export function pause(handle) {
  // F15 - IN: handle = the object returned by play() -- OUT: void
  throw new Error("TODO pause -- Track 2 - Day 6");
}
