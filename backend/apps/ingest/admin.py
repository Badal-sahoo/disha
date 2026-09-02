from django.contrib import admin

from .models import SmsMessage


@admin.register(SmsMessage)
class SmsMessageAdmin(admin.ModelAdmin):
    list_display = ("from_number", "body", "confidence", "incident", "received_at")
    list_filter = ("confidence",)
    search_fields = ("from_number", "body", "gateway_id")
