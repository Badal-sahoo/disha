"""dispatch — the only app that decides anything."""
from django.db import models


class Assignment(models.Model):
    class Policy(models.TextChoices):
        OPTIMIZED = "OPTIMIZED", "Optimised"
        GREEDY = "GREEDY", "Nearest available"
        GREEDY_SEVERITY = "GREEDY_SEVERITY", "Nearest, severity first"

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

    eta_min = models.FloatField()
    # The optimiser's score for this pairing. Keeping it is what makes
    # /api/dispatch/{code}/explain possible later.
    gain = models.FloatField(default=0.0)
    # Not decoration: this is what turns the dashboard A/B toggle into a
    # stored, replayable comparison instead of a live coin flip.
    policy = models.CharField(max_length=16, choices=Policy.choices,
                              default=Policy.OPTIMIZED)

    status = models.CharField(max_length=14, choices=Status.choices,
                              default=Status.PROPOSED, db_index=True)
    rescued_count = models.PositiveIntegerField(null=True, blank=True)

    dispatched_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-dispatched_at"]
        indexes = [models.Index(fields=["policy", "status"])]

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
