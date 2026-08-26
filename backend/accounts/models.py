"""accounts — deliberately tiny. Nobody wins a hackathon on permissions."""
from django.conf import settings
from django.db import models


class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        OPERATOR = "OPERATOR", "Ops room operator"
        RESPONDER = "RESPONDER", "Rescue team"

    user = models.OneToOneField(settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.OPERATOR)
    # Which unit this person drives. Lets /api/responder/assignment work
    # off the auth token alone, with no unit id in the URL.
    resource = models.ForeignKey("resources.Resource", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="crew")
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"
