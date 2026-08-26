from django.contrib import admin

from .models import Alert, Device


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("identifier", "event", "severity", "urgency", "active", "sent_at")
    list_filter = ("severity", "urgency", "active")
    search_fields = ("identifier", "event")
    readonly_fields = ("raw_xml",)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("token", "platform", "lat", "lon", "updated_at")
    list_filter = ("platform",)
    search_fields = ("token",)
