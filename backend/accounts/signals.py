"""Every User gets a Profile, automatically.

Without this, a superuser created with `createsuperuser` has no Profile row, so
`user.profile` raises Profile.DoesNotExist and GET /api/auth/me returns nulls
for role and resource_id -- which then breaks the frontend's role gate on the
very first login. Creating the row on user creation is one signal and removes
the whole class of bug.
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    """
    IN:  instance = User, created = bool
    OUT: None

    DB: INSERT INTO accounts_profile (user_id, role, resource_id, phone)
        only when the User row was just created.

    ROLE: superusers and staff get ADMIN, everyone else OPERATOR. A RESPONDER
    is always assigned deliberately -- through the admin or seed_demo -- because
    it must be paired with the resource that person drives.
    """
    if not created:
        return
    Profile.objects.get_or_create(
        user=instance,
        defaults={
            "role": Profile.Role.ADMIN if (instance.is_superuser or instance.is_staff)
            else Profile.Role.OPERATOR
        },
    )
