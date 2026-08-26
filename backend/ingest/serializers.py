"""ingest serializers -- machine callers, not browsers."""
from rest_framework import serializers

from .models import IvrSession, SmsMessage


class SmsMessageSerializer(serializers.ModelSerializer):
    """GET /api/sms/unparsed row -- the operator triage list.

    OUT: {
      id:          int,
      from_number: str,
      body:        str,       # ALWAYS present, even when parsing failed.
                              #   An unparsed message is still a human asking
                              #   for help, and a person can read it.
      received_at: str,       # ISO 8601
      gateway_id:  str,
      parsed:      obj|None,  # whatever parse_sms returned, or null
      confidence:  float,     # 0..1
      incident:    int|None,  # Incident PK once it became one
    }
    """
    class Meta:
        model = SmsMessage
        fields = ["id", "from_number", "body", "received_at", "gateway_id",
                  "parsed", "confidence", "incident"]
        read_only_fields = fields


class SmsIntakeSerializer(serializers.Serializer):
    """POST /api/sms -- from the Android handset gateway, never a browser.

    IN:  {
      from:        str,    # E.164 or local, whatever the handset sends
      body:        str,    # the raw 160 chars
      received_at: str,    # ISO 8601, when the HANDSET got it (not now())
      gateway_id:  str,    # the handset's own message id
    }
    OUT: {code: str|None, parsed: obj, confidence: float, incident_id: int|None}

    `from` is a Python keyword, so the field is declared with source="from_number"
    and the view reads validated_data["from_number"].

    DEDUPE: (gateway_id, received_at, from_number) is unique_together on the
    model -- that triple is the dedupe key when the handset re-sends.
    """
    from_number = serializers.CharField(max_length=20)
    body = serializers.CharField()
    received_at = serializers.DateTimeField()
    gateway_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")

    def to_internal_value(self, data):
        # The gateway posts {"from": ...}; map it before the normal path runs.
        if "from" in data and "from_number" not in data:
            data = {**data, "from_number": data["from"]}
        return super().to_internal_value(data)


class IvrStepSerializer(serializers.Serializer):
    """POST /api/ivr -- one keypress. Same endpoint for the browser simulator
    and a real TwiML webhook; the transport is swappable, the logic is not.

    IN:  {
      session_id: str,   # one per call
      digit:      str,   # "0".."9", "*", "#", or "" for the opening prompt
      from:       str,   # caller number
    }
    OUT: {
      prompt:      str,        # what to say/show next
      done:        bool,
      code:        str|None,   # incident code, once done
      incident_id: int|None,
      state:       str,        # "ASK_TYPE" | "ASK_PINCODE" | "ASK_COUNT" | "DONE"
    }
    """
    session_id = serializers.CharField(max_length=64)
    digit = serializers.CharField(max_length=2, allow_blank=True, default="")
    from_number = serializers.CharField(max_length=20)

    def to_internal_value(self, data):
        if "from" in data and "from_number" not in data:
            data = {**data, "from_number": data["from"]}
        return super().to_internal_value(data)


class IvrSessionSerializer(serializers.ModelSerializer):
    """OUT: {id, session_id, from_number, state, answers, incident, started_at}"""
    class Meta:
        model = IvrSession
        fields = ["id", "session_id", "from_number", "state", "answers",
                  "incident", "started_at"]
        read_only_fields = fields