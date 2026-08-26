from django.contrib import admin

from .models import Depot, Resource, Shelter, SupplyStock


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


class SupplyStockInline(admin.TabularInline):
    model = SupplyStock
    extra = 0


@admin.register(Depot)
class DepotAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "lat", "lon")
    search_fields = ("code", "name")
    inlines = [SupplyStockInline]


@admin.register(SupplyStock)
class SupplyStockAdmin(admin.ModelAdmin):
    list_display = ("depot", "item", "quantity")
    list_filter = ("item",)
