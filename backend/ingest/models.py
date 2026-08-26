"""ingest — the no-internet path. Build parsers.py first, before any of this."""
from django.db import models


class SmsMessage(models.Model):
    from_number = models.CharField(max_length=20, db_index=True)
    # Store the raw text ALWAYS, even when parsing fails. An unparsed message
    # is still a human asking for help, and a person can read it.
    body = models.TextField()
    received_at = models.DateTimeField(db_index=True)
    gateway_id = models.CharField(max_length=64, blank=True)
    parsed = models.JSONField(null=True, blank=True)
    confidence = models.FloatField(default=0.0)
    incident = models.ForeignKey(
        "reports.Incident", 
        null=True, 
        blank=True,
        on_delete=models.SET_NULL, 
        related_name="sms"
    )

    class Meta:
        ordering = ["-received_at"]
        unique_together = ("gateway_id", "received_at", "from_number")

    def __str__(self):
        return f"{self.from_number}: {self.body[:40]}"


class IvrSession(models.Model):
    session_id = models.CharField(max_length=64, unique=True)
    from_number = models.CharField(max_length=20)
    state = models.CharField(max_length=32, default="ASK_TYPE")
    answers = models.JSONField(default=dict)
    incident = models.ForeignKey(
        "reports.Incident", 
        null=True, 
        blank=True,
        on_delete=models.SET_NULL, 
        related_name="ivr"
    )
    started_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.session_id} @{self.state}"