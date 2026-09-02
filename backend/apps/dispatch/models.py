"""dispatch — the only app that decides anything."""
from django.db import models


class Assignment(models.Model):
    class Status(models.TextChoices):
        PROPOSED = "PROPOSED", "Proposed"          # a preview, not real yet
        DISPATCHED = "DISPATCHED", "Dispatched"
        ACCEPTED = "ACCEPTED", "Accepted by team"
        EN_ROUTE = "EN_ROUTE", "En route"
        ON_SCENE = "ON_SCENE", "On scene"
        TRANSPORTING = "TRANSPORTING", "Transporting"
        COMPLETE = "COMPLETE", "Complete"

    code = models.CharField(max_length=16, unique=True)          # ASG0088
    incident = models.ForeignKey("reports.Incident", on_delete=models.CASCADE,
                                 related_name="assignments")
    resource = models.ForeignKey("resources.Resource", on_delete=models.PROTECT,
                                 related_name="assignments")
    shelter = models.ForeignKey("resources.Shelter", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="incoming")

    # Where the unit was standing when this was committed.
    #
    # Not a duplicate of resource.lat/lon: committing MOVES the unit to where it
    # will end up, so that its next job is planned from the right place. That
    # overwrite destroyed the only record of where it set out from, and the map
    # ended up drawing each dispatch as a line from the destination to the
    # destination -- zero length, and nothing visible.
    origin_lat = models.FloatField(null=True, blank=True)
    origin_lon = models.FloatField(null=True, blank=True)

    # Which stop this is on the unit's run. 0 = go here first, 1 = then here.
    #
    # The optimiser is a 1:1 assignment problem, so it can only ever give a unit
    # ONE job. When there are more scenes than units, the leftovers used to get
    # nobody at all -- even when a boat finishing at a shelter was the obvious
    # next responder. A follow-up pass chains those on, and this column is what
    # says which order the crew runs them in.
    leg = models.PositiveSmallIntegerField(default=0)

    # Minutes from the unit's CURRENT position to this scene, including every
    # earlier leg on the run. leg 1 therefore already contains leg 0's travel
    # plus the time spent working that scene.
    eta_min = models.FloatField()
    # The optimiser's score for this pairing. Keeping it is what makes
    # /api/dispatch/{code}/explain possible later.
    gain = models.FloatField(default=0.0)
    status = models.CharField(max_length=14, choices=Status.choices,
                              default=Status.PROPOSED, db_index=True)
    rescued_count = models.PositiveIntegerField(null=True, blank=True)

    dispatched_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-dispatched_at"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self):
        return f"{self.code} {self.resource_id}->{self.incident_id}"


class Zone(models.Model):
    """A flooded or cut area. Severity 5 = impassable to anything without a hull."""
    class Source(models.TextChoices):
        OPERATOR = "OPERATOR", "Marked by operator"
        CAP = "CAP", "From alert feed"

    lat = models.FloatField()
    lon = models.FloatField()
    radius_km = models.FloatField()
    severity = models.PositiveSmallIntegerField()                # 1..5
    source = models.CharField(max_length=10, choices=Source.choices,
                              default=Source.OPERATOR)
    active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Zone sev{self.severity} r={self.radius_km}km"


class RoadGraph(models.Model):
    """A compiled road network, ready to route on.

    Built once by `manage.py seed_roadgraph` and loaded into memory at boot.
    The arrays are stored with numpy's own format rather than pickle, so loading
    one can never execute code.
    """
    name = models.CharField(max_length=64, unique=True)
    min_lat = models.FloatField()
    min_lon = models.FloatField()
    max_lat = models.FloatField()
    max_lon = models.FloatField()
    node_count = models.PositiveIntegerField()
    edge_count = models.PositiveIntegerField()
    data = models.BinaryField()
    built_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.node_count} nodes)"
