"""alerts serializers -- the CAP warnings the feed brought in."""
from rest_framework import serializers

from .models import Alert


class AlertSerializer(serializers.ModelSerializer):
    """identifier is the CAP id and is unique, so re-polling the same feed never
    duplicates a row. polygon is [[lat, lon], ...] -- LAT FIRST, as CAP writes
    it; the flip to [lon, lat] happens only at the GeoJSON boundary.

    raw_xml is deliberately NOT exposed: it is for you at 1 a.m. when a field
    parsed wrong, not for the wire.
    """
    class Meta:
        model = Alert
        fields = ["id", "identifier", "event", "severity", "urgency", "certainty",
                  "polygon", "sent_at", "expires_at", "active"]
        read_only_fields = fields
