from django.contrib import admin

from .models import Incident


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("code", "kind", "severity", "people", "status",
                    "corroborations", "cell_id", "reported_at")
    list_filter = ("status", "kind", "severity", "source")
    search_fields = ("code", "client_ref", "cell_id", "reporter_phone")
    readonly_fields = ("reported_at",)
