"""Deliberately tiny. Nobody has ever won a hackathon on permissions."""
from rest_framework.permissions import BasePermission

from .models import Profile


def _profile(request):
    """The caller's Profile, or None. One SELECT via the OneToOne accessor."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return None
    return getattr(user, "profile", None)


class IsOperator(BasePermission):
    """Guards every dashboard WRITE endpoint: True for ADMIN and OPERATOR.

    staff/superuser count as ADMIN -- someone created with createsuperuser may
    predate the Profile signal, and 403-ing the person who set the database up
    is not a useful failure mode.
    """
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser or user.is_staff:
            return True
        profile = _profile(request)
        return bool(profile and profile.role in (Profile.Role.ADMIN, Profile.Role.OPERATOR))


class IsResponder(BasePermission):
    """Guards the responder endpoints AND guarantees the view can reach
    request.user.profile.resource.

    A responder with no unit attached cannot answer for one, so returning True
    there would hand the view a None resource.
    """
    def has_permission(self, request, view):
        profile = _profile(request)
        return bool(profile
                    and profile.role == Profile.Role.RESPONDER
                    and profile.resource_id is not None)


def current_resource(request):
    """The unit this caller drives, or None. Why /api/responder/* needs no unit
    id in the URL.

    Reached through the FK accessor, so accounts never imports resources.
    """
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return None
    profile = (Profile.objects.select_related("resource")
               .filter(user=user).first())
    return profile.resource if profile else None
