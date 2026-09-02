from django.contrib import admin

from .models import Resource, Shelter


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "kind", "status", "capacity", "speed_kmph", "free_at")
    list_filter = ("kind", "status")
    search_fields = ("code", "name", "base_name")


@admin.register(Shelter)
class ShelterAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "occupancy", "capacity", "remaining")
    list_filter = ("status",)
    search_fields = ("code", "name")
