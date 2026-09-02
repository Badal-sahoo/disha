from django.urls import path

from .views import IncidentFromSmsView, SmsIntakeView, UnparsedSmsView

urlpatterns = [
    path("sms", SmsIntakeView.as_view(), name="sms-intake"),
    # unparsed must precede <pk>
    path("sms/unparsed", UnparsedSmsView.as_view(), name="sms-unparsed"),
    path("sms/<int:pk>/incident", IncidentFromSmsView.as_view(), name="sms-incident"),
]
