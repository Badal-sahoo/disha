"""reports — citizen incidents. Everything downstream reads from here."""
from django.db import models


class Incident(models.Model):
    class Kind(models.TextChoices):
        FLOOD = "FLOOD", "Flood"
        CYCLONE = "CYCLONE", "Cyclone"
        LANDSLIDE = "LANDSLIDE", "Landslide"

    class Source(models.TextChoices):
        APP = "APP", "Mobile app"
        SMS = "SMS", "SMS"
        IVR = "IVR", "IVR call"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        ASSIGNED = "ASSIGNED", "Assigned"
        RESOLVED = "RESOLVED", "Resolved"

    code = models.CharField(max_length=16, unique=True)          # INC0142
    # The phone generates this. Unique means a retried POST is a no-op
    # instead of a duplicate pin on the map.
    client_ref = models.CharField(max_length=64, unique=True, db_index=True)

    lat = models.FloatField()
    lon = models.FloatField()
    kind = models.CharField(max_length=12, choices=Kind.choices)
    severity = models.PositiveSmallIntegerField()                # 1..5
    people = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True)
    photo = models.ImageField(upload_to="reports/", null=True, blank=True)

    source = models.CharField(max_length=4, choices=Source.choices, default=Source.APP)
    reporter_phone = models.CharField(max_length=20, blank=True)

    # lat/lon rounded to 2dp (~1.1 km). Drives the heatmap AND the
    # corroboration count, so it must be indexed.
    cell_id = models.CharField(max_length=24, db_index=True)
    corroborations = models.PositiveIntegerField(default=1)

    status = models.CharField(max_length=10, choices=Status.choices,
                              default=Status.OPEN, db_index=True)
    reported_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Set once, on first arrival. Every benchmark number derives from this.
    first_response_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-reported_at"]
        indexes = [models.Index(fields=["status", "severity"])]

    def __str__(self):
        return f"{self.code} {self.kind} sev{self.severity}"
