from django.contrib import admin

from .models import Assignment, Zone


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("code", "incident", "resource", "status",
                    "eta_min", "gain", "dispatched_at")
    list_filter = ("status",)
    search_fields = ("code", "incident__code", "resource__code")
    autocomplete_fields = ("incident", "resource", "shelter")


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("id", "lat", "lon", "radius_km", "severity", "source", "active")
    list_filter = ("severity", "source", "active")
