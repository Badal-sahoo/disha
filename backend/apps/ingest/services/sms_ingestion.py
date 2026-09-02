"""The no-internet path: a phone gateway forwards an SMS to us."""
from apps.reports.models import Incident
from apps.reports.services.make_incident import create_incident

from ..models import SmsMessage
from .sms_parser import parse_sms


def receive_sms(from_number, body, received_at, gateway_id=""):
    """Store the raw text, parse it, and make an incident when we can place it.

    Returns {code, parsed, confidence, incident_id, needs_location}.

    A message we cannot place does NOT become a pin -- 0,0 is a real spot in the
    Atlantic, and guessing would send a boat to the wrong village. It waits in
    the triage queue instead.
    """
    # Raw first. If parsing explodes, the human-readable text still survives.
    sms, created = SmsMessage.objects.get_or_create(
        gateway_id=gateway_id,
        received_at=received_at,
        from_number=from_number,
        defaults={"body": body},
    )

    if not created and sms.incident_id:
        return {"code": sms.incident.code, "parsed": sms.parsed,
                "confidence": sms.confidence, "incident_id": sms.incident_id,
                "needs_location": False}

    draft, confidence = parse_sms(body, from_number)
    sms.parsed = draft
    sms.confidence = confidence

    if draft.get("lat") is None or draft.get("lon") is None:
        sms.save(update_fields=["parsed", "confidence"])
        return {"code": None, "parsed": draft, "confidence": confidence,
                "incident_id": None, "needs_location": True}

    incident = create_incident(draft, source=Incident.Source.SMS)
    sms.incident = incident
    sms.save(update_fields=["parsed", "confidence", "incident"])

    return {"code": incident.code, "parsed": draft, "confidence": confidence,
            "incident_id": incident.id, "needs_location": False}
