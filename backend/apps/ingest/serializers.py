"""ingest serializers -- machine callers, not browsers."""
from rest_framework import serializers

from .models import SmsMessage


class SmsMessageSerializer(serializers.ModelSerializer):
    """GET /api/sms/unparsed row -- the operator triage list. `body` is always
    present, even when parsing failed."""
    class Meta:
        model = SmsMessage
        fields = ["id", "from_number", "body", "received_at", "gateway_id",
                  "parsed", "confidence", "incident"]
        read_only_fields = fields


class SmsIntakeSerializer(serializers.Serializer):
    """POST /api/sms, from the Android handset gateway.

    received_at is when the HANDSET got the message, not now(). `from` is a
    Python keyword, so it is mapped to from_number below.
    """
    from_number = serializers.CharField(max_length=20)
    body = serializers.CharField()
    received_at = serializers.DateTimeField()
    gateway_id = serializers.CharField(max_length=64, required=False,
                                       allow_blank=True, default="")

    def to_internal_value(self, data):
        if "from" in data and "from_number" not in data:
            data = {**data, "from_number": data["from"]}
        return super().to_internal_value(data)
