"""resources — everything you can send somewhere, and everywhere you can send people to."""
from django.db import models


class Resource(models.Model):
    class Kind(models.TextChoices):
        TEAM = "TEAM", "Rescue team"
        BOAT = "BOAT", "Boat"
        TRUCK = "TRUCK", "Truck"
        AMBULANCE = "AMBULANCE", "Ambulance"

    class Status(models.TextChoices):
        IDLE = "IDLE", "Idle"
        ENROUTE = "ENROUTE", "En route"
        ONSCENE = "ONSCENE", "On scene"
        TRANSPORTING = "TRANSPORTING", "Transporting"
        OUT_OF_SERVICE = "OUT_OF_SERVICE", "Out of service"

    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=12, choices=Kind.choices)

    lat = models.FloatField()
    lon = models.FloatField()

    # e.g. ["BOAT", "ROPE_RESCUE"]. A JSON list beats a M2M table here
    # because you only ever read the whole thing at once.
    capabilities = models.JSONField(default=list)
    capacity = models.PositiveIntegerField(default=10)
    speed_kmph = models.FloatField(default=35.0)

    status = models.CharField(max_length=16, choices=Status.choices,
                              default=Status.IDLE, db_index=True)
    free_at = models.DateTimeField(null=True, blank=True)
    base_name = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} ({self.get_status_display()})"


class Shelter(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        FULL = "FULL", "Full"
        INACCESSIBLE = "INACCESSIBLE", "Inaccessible"

    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=80)
    lat = models.FloatField()
    lon = models.FloatField()
    capacity = models.PositiveIntegerField()
    occupancy = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.OPEN)

    @property
    def remaining(self) -> int:
        """Never store this as a column — a stored copy drifts from reality."""
        if self.status != self.Status.OPEN:
            return 0
        return max(self.capacity - self.occupancy, 0)

    def __str__(self):
        return f"{self.code} {self.occupancy}/{self.capacity}"


class Depot(models.Model):
    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=80)
    lat = models.FloatField()
    lon = models.FloatField()

    def __str__(self):
        return self.code


class SupplyStock(models.Model):
    class Item(models.TextChoices):
        KIT = "KIT", "Survival kit"
        WATER = "WATER", "Water"
        FOOD = "FOOD", "Food"
        MEDICAL = "MEDICAL", "First aid"

    depot = models.ForeignKey(Depot, on_delete=models.CASCADE, related_name="stock")
    item = models.CharField(max_length=10, choices=Item.choices)
    quantity = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("depot", "item")

    def __str__(self):
        return f"{self.depot.code} {self.item} x{self.quantity}"
