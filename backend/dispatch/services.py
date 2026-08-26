"""S5 -- the dispatch orchestrator. The only thing in this project that decides
anything. Everything else moves data around.

Debounced, synchronous, and deliberately NOT a Celery task: the solve takes
under a millisecond, so a queue would add latency and a whole failure mode for
nothing.

IMPORT MAP (blueprint 01): dispatch imports reports, resources and accounts, and
calls realtime.broadcast(). Nothing imports dispatch except the views above it
and alerts (which sits higher). engine.py imports NOTHING from Django -- that is
what keeps the allocator unit-testable with no database.
"""


def run_cycle(trigger):
    """The whole loop, in one call.

    IN:  trigger = str      # "report" | "unit_freed" | "zone" | "alert" | "manual"
                            # recorded for the timeline; it does not change behaviour
    OUT: {
           made:    int,    # assignments committed this cycle
           skipped: bool,   # True when the debounce floor swallowed the call
           reason:  str,    # "" | "debounced" | "no_open_incidents" | "no_units"
         }

    USES:
      resources.services.release_due(now)          -> int
      dispatch.services.open_set(now)              -> (list[Incident], QuerySet[Resource])
      dispatch.services.build_plan(incs, units, policy)  -> list[Assignment]  (unsaved)
      dispatch.services.commit_plan(assignments)   -> int
      dispatch.services.compute_kpi(policy)        -> dict
      realtime.broadcast(event_type, data)         -> None

    DB:  release_due does one UPDATE; open_set does two SELECTs; commit_plan
         runs one transaction. Nothing else touches the database.

    DEBOUNCE -- do not skip this:
      Keep `_last_run_at` in a module-level variable and return
      {"made": 0, "skipped": True, "reason": "debounced"} when
      now - _last_run_at < settings.DISPATCH_MIN_INTERVAL_SEC (default 2).
      Without it, fifty SMS arriving together produce fifty solves. A module
      global is correct here precisely because the solve is synchronous and
      single-process; if you later run multiple workers, move it to a Redis key.

    EMITS: broadcast("kpi.update", compute_kpi("OPTIMIZED"))  at the end of every
           cycle that actually ran.

    CALLED BY:
      reports/views.py   ReportListCreateView.create   trigger="report"
      ingest/views.py    SmsIntakeView / IvrView       trigger="report"
      dispatch/views.py  ZoneListCreateView / ZoneDetailView  trigger="zone"
      dispatch/views.py  AssignmentStatusView (on COMPLETE)   trigger="unit_freed"
      alerts/services.py preposition()                 trigger="alert"
      -- three completely different doors, one decision maker. That is the whole
         architecture in one sentence.
    """
    raise NotImplementedError("dispatch.services.run_cycle -- Track 1 - Day 2")


def open_incidents():
    """Unassigned incidents only.

    IN:  --
    OUT: QuerySet[Incident]      # status = "OPEN"

    DB:  SELECT * FROM reports_incident WHERE status = 'OPEN'
         status is db_index'd, and Meta.indexes has (status, severity).

    Anything already ASSIGNED stays out of the solve -- in-flight work never
    re-enters, because you cannot recall a boat that is 80% of the way there.
    """
    raise NotImplementedError("dispatch.services.open_incidents -- Track 1 - Day 2")


def open_set(now):
    """Both halves of the solve's input, fetched together.

    IN:  now = datetime
    OUT: (incidents, units)
           incidents = list[reports.models.Incident]     # status="OPEN"
           units     = list[resources.models.Resource]   # IDLE and free

    USES: dispatch.services.open_incidents()
          resources.services.available_units(now)
    """
    raise NotImplementedError("dispatch.services.open_set -- Track 1 - Day 2")


def build_plan(incidents, units, policy="OPTIMIZED"):
    """ORM rows -> plain dataclasses -> engine.py -> Assignment rows back.

    This conversion costs about fifteen lines. In exchange the entire allocation
    logic runs in a unit test with no database, no migrations and no fixtures --
    which is how test_engine.py already passes ten checks in under a second.
    engine.py must never see a Django model.

    IN:  incidents = list[reports.models.Incident]
         units     = list[resources.models.Resource]
         policy    = str    # "OPTIMIZED" | "GREEDY" | "GREEDY_SEVERITY"

    OUT: list[dispatch.models.Assignment]
         UNSAVED instances with status="PROPOSED". The caller decides whether
         they are a preview (GET /api/dispatch/plan) or get committed.
         Each carries: incident, resource, shelter, eta_min, gain, policy.

    USES -- from dispatch.engine (already in this folder, zero Django imports):
      engine.Incident(id, lat, lon, kind, severity, people_affected,
                      reported_at, corroborations, needs_evacuation)
                                          # reported_at in MINUTES or epoch seconds,
                                          # consistent with the `now` you pass below
      engine.Resource(id, lat, lon, kind, capabilities: set[str], capacity,
                      speed_kmph, status, free_at)
                                          # capabilities is a SET here, a JSON list
                                          # on the model -- convert with set(...)
      engine.Shelter(id, lat, lon, capacity, occupancy, status)
      engine.BlockedZone(lat, lon, radius_km, severity)
      engine.optimize(incidents, resources, now, blocked) -> list[engine.Assignment]
      engine.greedy_nearest(incidents, resources, now, blocked, severity_first: bool)
                                                          -> list[engine.Assignment]
      engine.choose_shelter(lat, lon, people, shelters, blocked) -> engine.Shelter | None
      engine.Assignment fields: (incident_id, resource_id, eta_min, slot, gain)

      policy -> engine call:
        "OPTIMIZED"       -> engine.optimize(...)
        "GREEDY"          -> engine.greedy_nearest(..., severity_first=False)
        "GREEDY_SEVERITY" -> engine.greedy_nearest(..., severity_first=True)

      dispatch.services.active_zones()      -> list[Zone]  (cached)
      common.codes.next_code("ASG", Assignment) -> str      # "ASG0088"

    DB:  read-only. One SELECT on resources_shelter (status='OPEN') for the
         shelter stage. Nothing is written here.

    GOTCHA: engine ids are STRINGS. Map them back to PKs with a dict built
            before the call -- {str(inc.pk): inc} -- or the round trip silently
            drops every assignment.
    """
    raise NotImplementedError("dispatch.services.build_plan -- Track 1 - Day 2")


def commit_plan(assignments):
    """One transaction: save rows, reserve beds, mark units busy, flip incidents.

    IN:  assignments = list[dispatch.models.Assignment]   # unsaved, from build_plan
    OUT: {
           committed: int,
           rejected:  [{code: str, reason: str}, ...],
         }
         reason is "unit_taken" | "shelter_full" | "incident_closed"

    USES:
      resources.services.reserve_shelter(shelter, people) -> bool
      resources.services.set_busy(resource, until, lat, lon) -> None
      realtime.broadcast(event_type, data)  and  realtime.notify_unit(code, type, data)
      dispatch.serializers.AssignmentSerializer

    DB -- all of it inside ONE transaction.atomic():
      1. SELECT resources_resource FOR UPDATE for every unit in the batch,
         re-checking status='IDLE'. A unit taken since the plan was fetched is
         REJECTED, not overwritten -- this is why commit returns a rejected[].
      2. reserve_shelter() per assignment (its own select_for_update on the
         shelter row; reserve at DISPATCH time, not on arrival).
      3. INSERT dispatch_assignment: code, status='DISPATCHED', dispatched_at=now
      4. UPDATE reports_incident SET status='ASSIGNED' WHERE id IN (...)
      5. set_busy() per unit: status='ENROUTE', free_at, and lat/lon moved to
         where it will END UP (the shelter, not the incident).

    EMITS (after the transaction commits, never inside it -- a broadcast from
           inside a transaction that then rolls back tells the dashboard a lie):
      broadcast("assignment.new", AssignmentSerializer(a).data)   per row
      notify_unit(a.resource.code, "assignment.new", <same dict>) per row
      broadcast("incident.update", {"id": ..., "status": "ASSIGNED"})
      broadcast("shelter.update", {...})  per shelter touched

    CALLED BY: dispatch/services.py run_cycle(), dispatch/views.py CommitView
    """
    raise NotImplementedError("dispatch.services.commit_plan -- Track 1 - Day 3")


def active_zones():
    """Cut roads and flooded areas, cached in memory.

    IN:  --
    OUT: list[dispatch.models.Zone]      # active=True

    DB:  SELECT * FROM dispatch_zone WHERE active = TRUE   (active is db_index'd)

    CACHING: hold the list in a module-level variable and invalidate it whenever
    a zone is created or deleted -- dispatch/views.py already calls
    invalidate_zone_cache() on both paths. Zones change a handful of times per
    operation and are read on every single solve, so this is the one cache in
    the project that pays for itself.
    """
    raise NotImplementedError("dispatch.services.active_zones -- Track 1 - Day 3")


def invalidate_zone_cache():
    """Drop the active_zones() cache. Called by the zone create/delete views.

    IN:  --
    OUT: None

    Also the right place to drop the Dijkstra cache and re-warm the road graph
    once USE_ROAD_GRAPH is on -- roadnet.apply_zones(zones) then roadnet.warm().
    Measured end to end at ~47 ms, which is what makes the road-cut editor feel
    instant on stage.
    """
    raise NotImplementedError("dispatch.services.invalidate_zone_cache -- Track 1 - Day 3")


def compute_kpi(policy="OPTIMIZED"):
    """The five numbers on the dashboard strip, computed PER POLICY so the A/B
    toggle shows a real difference instead of the same figures twice.

    IN:  policy = str    # "OPTIMIZED" | "GREEDY" | "GREEDY_SEVERITY"
    OUT: {
           crit_mean:    float,   # mean minutes, reported_at -> first_response_at,
                                  #   over severity >= 4 incidents that were reached
           crit_p90:     float,   # 90th percentile of the same list
           crit_sla_pct: float,   # 0..100, share reached within the SLA
                                  #   (settings.DISPATCH_HORIZON_MIN is the horizon;
                                  #    pick an SLA and keep it fixed across policies)
           unreached:    int,     # OPEN incidents, severity >= 4, no assignment
           awaiting:     int,     # OPEN incidents with no assignment, any severity
         }
         Return zeros, not None, when there is nothing to average -- the KPI
         strip must render on an empty database.

    DB:  SELECT reported_at, first_response_at FROM reports_incident
           WHERE severity >= 4 AND first_response_at IS NOT NULL
           JOIN dispatch_assignment ON assignment.incident_id = incident.id
           WHERE assignment.policy = %s AND assignment.status <> 'PROPOSED'
         dispatch_assignment has an index on (policy, status) for exactly this.
         Percentile in Python -- numpy.percentile on a list of a few hundred
         floats beats a window function you have to debug at 1 a.m.

    CALLED BY: dispatch/views.py StateView, PlanView, KpiView; run_cycle() at
               the end of every cycle -> broadcast("kpi.update", <this dict>)
    """
    raise NotImplementedError("dispatch.services.compute_kpi -- Track 1 - Day 3")


def explain(assignment):
    """Recompute the four priority terms behind one dispatch. Twenty lines, and
    it is your answer to "why should anyone trust this?"

    IN:  assignment = dispatch.models.Assignment
    OUT: {
           w:       float,        # total priority 0..1
           eta_min: float,
           gain:    float,        # w * (DISPATCH_HORIZON_MIN - eta_min)
           terms: {
             severity:      float,   # engine.W_SEVERITY * (severity-1)/4
             people:        float,   # engine.W_PEOPLE   * min(people/50, 1)
             age:           float,   # engine.W_AGE      * min(age_min/45, 1)
             corroboration: float,   # engine.W_CORROB   * min((corrob-1)/4, 1)
           },
           alternatives: [{resource_code, eta_min, gain, reason}, ...],
         }
         The four terms must SUM to w. If they do not, you have drifted from
         engine.Incident.priority() -- read the weights off the engine module
         (engine.W_SEVERITY etc.) rather than retyping the numbers here.

    USES: dispatch.engine  W_SEVERITY, W_PEOPLE, W_AGE, W_CORROB,
                           PEOPLE_SATURATION, AGE_SATURATION_MIN, CORROB_SATURATION,
                           travel_minutes(res, lat, lon, blocked)
          dispatch.services.active_zones()

    DB:  SELECT the assignment with select_related("incident", "resource").
         `alternatives` costs one more SELECT over idle units -- it is optional;
         ship the four terms first.

    CALLED BY: dispatch/views.py ExplainView (GET /api/dispatch/{code}/explain)
    CONSUMED BY: frontend features/dispatch ExplainDrawer
    """
    raise NotImplementedError("dispatch.services.explain -- Track 1 - Day 3")


def apply_status(assignment, new_status, note="", rescued=None):
    """Walk an assignment along its lifecycle and apply every side effect.

    IN:  assignment = Assignment
         new_status = str    # "ACCEPTED"|"EN_ROUTE"|"ON_SCENE"|"TRANSPORTING"|"COMPLETE"
         note       = str
         rescued    = int | None   # only meaningful with COMPLETE
    OUT: {
           ok:   True,
           next: str | None,   # the status the app should offer next, None at COMPLETE
         }

    TRANSITIONS and their side effects:
      ACCEPTED     -> freeze it. The optimiser may reassign a DISPATCHED job;
                      after accept it must not.
      EN_ROUTE     -> resource.status = "ENROUTE"
      ON_SCENE     -> assignment.arrived_at = now
                      reports.services.mark_first_response(incident, now)
                      resource.status = "ONSCENE"
      TRANSPORTING -> resource.status = "TRANSPORTING"
      COMPLETE     -> assignment.completed_at = now, rescued_count = rescued
                      incident.status = "RESOLVED"
                      resource.status = "IDLE", free_at = now
                      then run_cycle("unit_freed") -- a freed unit is exactly
                      when re-solving pays off

    RAISES: ValueError on an illegal jump (e.g. DISPATCHED -> COMPLETE).
            Keep the legal-transition map in this module, not in the view.

    DB:  UPDATE dispatch_assignment (status + the relevant timestamp)
         UPDATE resources_resource  (status, free_at)
         UPDATE reports_incident    (status, first_response_at) where applicable
         One transaction.atomic().

    EMITS: broadcast("assignment.update", {id, code, status, ts})
           notify_unit(resource.code, "assignment.update", <same>)
           broadcast("resource.update", ResourceSerializer(resource).data)
           broadcast("incident.update", {id, status}) on COMPLETE

    CALLED BY: dispatch/views.py AssignmentStatusView, AssignmentHeadcountView
    """
    raise NotImplementedError("dispatch.services.apply_status -- Track 1 - Day 4")


def update_unit_location(resource, lat, lon, ts=None):
    """The 20-second beacon. Also updates the unit's origin for the next solve --
    a unit that finishes at a shelter starts its next job from there.

    IN:  resource = Resource
         lat, lon = float
         ts       = datetime | None    # None -> now()
    OUT: None

    DB:  UPDATE resources_resource SET lat=%s, lon=%s WHERE id=%s
         One row, one column pair. Do NOT write a history table here -- 28 units
         at 20 s is 5000 rows an hour and nothing reads them.

    EMITS: broadcast("resource.update", {id, lat, lon, status, free_at})
           The dashboard interpolates between pings (features/fleet animateUnit)
           so movement looks continuous at a 20 s interval.

    CALLED BY: dispatch/views.py ResponderLocationView
    """
    raise NotImplementedError("dispatch.services.update_unit_location -- Track 1 - Day 4")


def route_polyline(from_lat, from_lon, to_lat, to_lon, vclass="TRUCK"):
    """Flood-aware route geometry. The one place you must not hand off to
    Google -- it does not know the causeway washed out an hour ago.

    IN:  from_lat, from_lon, to_lat, to_lon = float
         vclass = str    # "TRUCK" | "BOAT" | "TEAM" | "AMBULANCE"
    OUT: {
           polyline: [[lat, lon], ...],   # [[lat,lon]] order, NOT GeoJSON order
           minutes:  float,
         }

    USES: dispatch.roadnet -- compile_graph / snap / warm / costs_from are all
          delivered. The missing piece is walking the predecessor array:
          scipy.sparse.csgraph.dijkstra(..., return_predecessors=True), then
          walk back from the destination node.

    FALLBACK when settings.USE_ROAD_GRAPH is False (the default): return the
    straight segment [[from_lat, from_lon], [to_lat, to_lon]] and
    engine.travel_minutes() for the minutes. The dashboard renders either
    without knowing the difference -- ship this fallback first.

    CALLED BY: dispatch/views.py RouteView (GET /api/route)
    CONSUMED BY: mobile F6 navigation, dashboard F9 assignment lines
    """
    raise NotImplementedError("dispatch.services.route_polyline -- Track 5 - Day 4")


def build_state(bbox=None):
    """The full snapshot. Page load, and after EVERY WebSocket reconnect.

    IN:  bbox = {min_lon, min_lat, max_lon, max_lat} | None
    OUT: {
           t:           str,    # ISO 8601 server time -- the client stamps its store with it
           incidents:   [IncidentSerializer, ...],       # status != RESOLVED
           resources:   [ResourceSerializer, ...],       # all of them
           shelters:    [ShelterSerializer, ...],
           zones:       [ZoneSerializer, ...],           # active only
           assignments: [AssignmentSerializer, ...],     # status != COMPLETE, != PROPOSED
           alerts:      [AlertSerializer, ...],          # active only
           kpi:         {crit_mean, crit_p90, crit_sla_pct, unreached, awaiting},
         }

    USES: every app's serializer, plus compute_kpi("OPTIMIZED").
          alerts is the one upward-looking import in this module -- dispatch may
          import alerts.models for a read, but alerts imports dispatch for
          preposition(), so import it INSIDE the function, not at module level.

    DB:  six SELECTs. Use select_related on assignments (incident, resource,
         shelter) or the serializer fires 3 queries per row.
         Apply common.geo.bbox_filter() to incidents, resources and shelters
         when bbox is not None.

    WHY IT MATTERS: deltas missed while a socket was disconnected are gone
    forever -- there is no replay buffer. Every reconnect calls this and
    rebuilds from scratch. Skip that and the dashboard drifts silently out of
    sync over a long demo, which is the worst failure mode there is: it looks
    fine, and it is wrong.

    CALLED BY: dispatch/views.py StateView (GET /api/state)
    """
    raise NotImplementedError("dispatch.services.build_state -- Track 1 - Day 1")


def timeline_events(start, end):
    """Every state-changing event in order. The event log IS the timeline.

    IN:  start, end = datetime
    OUT: [{t: datetime, type: str, data: dict}, ...]   # ascending by t
         `type` uses the same 10 strings as the WebSocket events, so F15 can
         replay them through the SAME applyDelta reducer the live dashboard uses.

    DB:  There is no event table in the 12 models. Two honest options:
         a) synthesise the log from timestamps you already store --
            incident.reported_at -> "incident.new",
            assignment.dispatched_at -> "assignment.new",
            assignment.arrived_at/completed_at -> "assignment.update",
            incident.first_response_at -> "incident.update".
            UNION them, sort by t. No migration, and it cannot drift from the
            real rows. Do this one.
         b) add an Event model and write to it from broadcast().
            Truthful, but it doubles every write path.

    CALLED BY: dispatch/views.py TimelineView (GET /api/timeline)
    """
    raise NotImplementedError("dispatch.services.timeline_events -- Track 5 - Day 6")


def after_action_report(start, end, fmt="csv"):
    """What a real district authority files afterwards.

    IN:  start, end = datetime
         fmt        = str    # "csv" | "pdf"
    OUT: (bytes, content_type, filename)
         e.g. (b"...", "text/csv", "ps05-after-action-2026-08-26.csv")

    CONTENT: response times by severity, unserved incidents, shelter
             utilisation, and every dispatch with its `gain` -- the gain column
             is what makes the report auditable rather than a summary.

    DB:  the same reads as compute_kpi plus a full assignment dump over the window.

    CALLED BY: dispatch/views.py AfterActionView (GET /api/after-action)
    """
    raise NotImplementedError("dispatch.services.after_action_report -- Track 5 - Day 6")
