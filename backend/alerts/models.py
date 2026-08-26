"""alerts — warnings in from SACHET/IMD, notifications out to citizens."""
from django.db import models


class Alert(models.Model):
    # CAP identifier. Unique means re-polling the same feed never duplicates,
    # so the poller can run as often as you like.
    identifier = models.CharField(max_length=128, unique=True)
    event = models.CharField(max_length=120)                     # "Cyclone Warning"
    severity = models.CharField(max_length=20)                   # Minor..Extreme
    urgency = models.CharField(max_length=20, blank=True)
    certainty = models.CharField(max_length=20, blank=True)
    polygon = models.JSONField(default=list)                     # [[lat, lon], ...]
    sent_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    # Keep the original. When a field parses wrong at 1am you will want it.
    raw_xml = models.TextField(blank=True)
    active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.event} ({self.severity})"


class Device(models.Model):
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=10, default="ANDROID")
    # Round to ~1km before saving. You never need street precision to warn
    # someone that a cyclone is coming.
    lat = models.FloatField()
    lon = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.platform} {self.token[:12]}..."
