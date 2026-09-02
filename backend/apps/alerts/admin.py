from django.contrib import admin

from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("identifier", "event", "severity", "urgency", "active", "sent_at")
    list_filter = ("severity", "urgency", "active")
    search_fields = ("identifier", "event")
    readonly_fields = ("raw_xml",)
