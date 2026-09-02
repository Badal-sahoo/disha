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
    """Somewhere people can be taken to. Two different kinds of somewhere.

    A cyclone shelter takes an evacuated village. A hospital takes a casualty.
    They were the same row type, so an ambulance carrying an unconscious man was
    routed to a community hall with no doctor in it -- which read fine on the
    map and would have killed him.
    """
    class Kind(models.TextChoices):
        SHELTER = "SHELTER", "Cyclone shelter"
        HOSPITAL = "HOSPITAL", "Hospital"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        FULL = "FULL", "Full"
        INACCESSIBLE = "INACCESSIBLE", "Inaccessible"

    code = models.CharField(max_length=24, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices,
                            default=Kind.SHELTER, db_index=True)
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
