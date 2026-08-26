"""The ten event types, in one place, so the backend and the frontend cannot
drift apart. The frontend mirror of this list lives in
src/shared/utils/constants.js -- change one, change both.

Deltas only, never full state. A busy dashboard drowns otherwise.
"""

INCIDENT_NEW = "incident.new"          # a report cleared ingest            -> ops
INCIDENT_UPDATE = "incident.update"    # corroboration/status/headcount     -> ops
RESOURCE_UPDATE = "resource.update"    # beacon ping or status transition   -> ops
ASSIGNMENT_NEW = "assignment.new"      # a dispatch was committed           -> ops, unit
ASSIGNMENT_UPDATE = "assignment.update"  # accepted, arrived, completed     -> ops, unit
SHELTER_UPDATE = "shelter.update"      # beds reserved, or an operator edit -> ops
ZONE_NEW = "zone.new"                  # a road was cut                     -> ops, unit
ZONE_REMOVED = "zone.removed"          # water receded                      -> ops, unit
ALERT_NEW = "alert.new"                # a CAP poll found a new warning     -> ops
KPI_UPDATE = "kpi.update"              # end of every dispatch cycle        -> ops

ALL = (
    INCIDENT_NEW, INCIDENT_UPDATE, RESOURCE_UPDATE, ASSIGNMENT_NEW,
    ASSIGNMENT_UPDATE, SHELTER_UPDATE, ZONE_NEW, ZONE_REMOVED, ALERT_NEW,
    KPI_UPDATE,
)

OPS_GROUP = "ops"


def unit_group(code):
    """Channel-layer group name for one rescue unit.

    IN:  code = str      # Resource.code, e.g. "BOAT-04"
    OUT: str             # "unit_BOAT-04"

    Channels group names allow only ASCII alphanumerics, hyphens, underscores
    and periods, max 100 chars -- Resource.code is max 24 and already conforms.
    """
    return f"unit_{code}"
