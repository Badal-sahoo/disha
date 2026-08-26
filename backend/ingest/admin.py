from django.contrib import admin

from .models import IvrSession, SmsMessage


@admin.register(SmsMessage)
class SmsMessageAdmin(admin.ModelAdmin):
    list_display = ("from_number", "body", "confidence", "incident", "received_at")
    list_filter = ("confidence",)
    search_fields = ("from_number", "body", "gateway_id")


@admin.register(IvrSession)
class IvrSessionAdmin(admin.ModelAdmin):
    list_display = ("session_id", "from_number", "state", "incident", "started_at")
    list_filter = ("state",)
    search_fields = ("session_id", "from_number")
