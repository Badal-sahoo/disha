"""Every User gets a Profile, automatically.

Without this a superuser made with createsuperuser has no Profile row, so
user.profile raises and GET /api/auth/me returns nulls for role -- which breaks
the frontend's role gate on the very first login. One signal removes the whole
class of bug.

Superusers and staff get ADMIN, everyone else OPERATOR. A RESPONDER is always
assigned deliberately, through the admin or seed_demo, because it must be paired
with the unit that person drives.
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    if not created:
        return
    Profile.objects.get_or_create(
        user=instance,
        defaults={"role": Profile.Role.ADMIN
                  if (instance.is_superuser or instance.is_staff)
                  else Profile.Role.OPERATOR},
    )
