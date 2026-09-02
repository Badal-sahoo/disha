"""ingest views -- machine callers, not browsers.

POST /api/sms is AllowAny because a phone gateway has no JWT. It is guarded by a
shared-secret header instead; that endpoint must not be open.
"""
import hmac

from django.conf import settings
from django.db.models import Q
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dispatch.services.assign import run_cycle
from apps.reports.serializers import IncidentSerializer

from .models import SmsMessage
from .serializers import SmsIntakeSerializer, SmsMessageSerializer
from .services.sms_ingestion import receive_sms


class SmsIntakeView(APIView):
    """POST /api/sms -- one forwarded text message."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        # Constant-time compare: the secret is short and the endpoint is public.
        if not hmac.compare_digest(request.headers.get("X-Gateway-Secret", ""),
                                   settings.SMS_GATEWAY_SECRET):
            raise ValueError("Bad or missing X-Gateway-Secret header.")

        payload = SmsIntakeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        result = receive_sms(data["from_number"], data["body"],
                             data["received_at"], data.get("gateway_id", ""))

        if result["incident_id"] is not None:
            run_cycle(trigger="report")
        return Response(result)


class UnparsedSmsView(generics.ListAPIView):
    """GET /api/sms/unparsed -- messages still needing a human, newest first."""

    serializer_class = SmsMessageSerializer

    def get_queryset(self):
        return (SmsMessage.objects
                .filter(Q(incident__isnull=True) | Q(confidence__lt=0.5))
                .select_related("incident"))


class IncidentFromSmsView(APIView):
    """GET /api/sms/{id}/incident -- the incident a message produced, if any."""

    def get(self, request, pk):
        sms = generics.get_object_or_404(SmsMessage.objects.select_related("incident"), pk=pk)
        return Response(IncidentSerializer(sms.incident).data if sms.incident else None)
