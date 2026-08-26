"""ingest views -- machine callers, not browsers.

POST /api/sms and POST /api/ivr are AllowAny at the DRF level because a handset
gateway has no JWT. They are guarded instead by a shared secret header. That
endpoint must not be open.
"""
from django.conf import settings
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from dispatch.services import run_cycle
from reports.models import Incident
from reports.serializers import IncidentSerializer
from reports.services import create_incident

from .models import IvrSession, SmsMessage
from .parsers import ivr_next, parse_sms
from .serializers import IvrStepSerializer, SmsIntakeSerializer, SmsMessageSerializer


class GatewaySecretMixin:
    """Shared-secret guard for the two machine endpoints.

    IN:  request header  X-Gateway-Secret: <settings.SMS_GATEWAY_SECRET>
    OUT: raises ValueError -> HTTP 400 when it is missing or wrong.

    A constant-time compare is not overkill here -- the secret is short and the
    endpoint is public.
    """
    def check_secret(self, request):
        import hmac

        sent = request.headers.get("X-Gateway-Secret", "")
        if not hmac.compare_digest(sent, settings.SMS_GATEWAY_SECRET):
            raise ValueError("Bad or missing X-Gateway-Secret header.")


class SmsIntakeView(GatewaySecretMixin, APIView):
    """POST /api/sms

    IN:  header X-Gateway-Secret
         {from: str, body: str, received_at: ISO 8601, gateway_id: str}
    OUT: 200 {code: str|None, parsed: obj, confidence: float, incident_id: int|None}
         400 bad secret or payload

    Stores the raw message ALWAYS, then parses, then creates an incident.
    A message that cannot be parsed still lands as a low-confidence incident and
    still appears in GET /api/sms/unparsed for a human to triage.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        self.check_secret(request)

        payload = SmsIntakeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        # Raw first. If parsing explodes, the human-readable text still survives.
        sms, created = SmsMessage.objects.get_or_create(
            gateway_id=data.get("gateway_id", ""),
            received_at=data["received_at"],
            from_number=data["from_number"],
            defaults={"body": data["body"]},
        )
        if not created and sms.incident_id:
            # Redelivery of a message we already turned into an incident.
            return Response({
                "code": sms.incident.code,
                "parsed": sms.parsed,
                "confidence": sms.confidence,
                "incident_id": sms.incident_id,
            })

        draft, confidence = parse_sms(data["body"], data["from_number"])
        sms.parsed, sms.confidence = draft, confidence

        incident = create_incident(draft, source=Incident.Source.SMS)
        sms.incident = incident
        sms.save(update_fields=["parsed", "confidence", "incident"])

        run_cycle(trigger="report")

        return Response({
            "code": incident.code,
            "parsed": draft,
            "confidence": confidence,
            "incident_id": incident.id,
        })


class IvrView(GatewaySecretMixin, APIView):
    """POST /api/ivr

    IN:  header X-Gateway-Secret
         {session_id: str, digit: str, from: str}
    OUT: 200 {prompt: str, done: bool, code: str|None, incident_id: int|None, state: str}
         400 bad secret or payload

    Drives the DTMF state machine one keypress at a time. The browser simulator
    and a TwiML webhook both post here -- the transport is swappable, the logic
    is not.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        self.check_secret(request)

        payload = IvrStepSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        session, _ = IvrSession.objects.get_or_create(
            session_id=data["session_id"],
            defaults={"from_number": data["from_number"]},
        )

        prompt, done = ivr_next(session, data["digit"])

        incident = session.incident
        if done and incident is None:
            draft = dict(session.answers)
            draft["reporter_phone"] = session.from_number
            incident = create_incident(draft, source=Incident.Source.IVR)
            session.incident = incident
            session.save(update_fields=["incident"])
            run_cycle(trigger="report")

        return Response({
            "prompt": prompt,
            "done": done,
            "code": incident.code if incident else None,
            "incident_id": incident.id if incident else None,
            "state": session.state,
        })


class UnparsedSmsView(generics.ListAPIView):
    """GET /api/sms/unparsed

    IN:  -- (operator JWT)
    OUT: 200 [SmsMessageSerializer, ...]   newest first

    The triage queue: everything the parser was not confident about. A human
    reads the raw body and fixes the pin by hand.
    """
    serializer_class = SmsMessageSerializer

    def get_queryset(self):
        return SmsMessage.objects.filter(confidence__lt=0.5).select_related("incident")


class IncidentFromSmsView(APIView):
    """GET /api/sms/{id}/incident -- convenience for the triage panel.

    IN:  id = int in the path
    OUT: 200 IncidentSerializer | null
         404 unknown sms id
    """
    def get(self, request, pk):
        sms = generics.get_object_or_404(SmsMessage.objects.select_related("incident"), pk=pk)
        return Response(IncidentSerializer(sms.incident).data if sms.incident else None)