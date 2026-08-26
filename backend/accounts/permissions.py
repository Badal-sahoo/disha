"""Deliberately tiny. Nobody has ever won a hackathon on permissions.

Three things live here and the views already reference them by name -- fill in
the bodies and every guarded endpoint starts enforcing at once.
"""
from .models import Profile
from rest_framework.permissions import BasePermission


class IsOperator(BasePermission):
    """Guards every dashboard WRITE endpoint.

    IN:  request  -- request.user is a django User; request.user.profile.role
                     is "ADMIN" | "OPERATOR" | "RESPONDER"
         view     -- the APIView instance (unused)
    OUT: bool     -- True for ADMIN and OPERATOR, False otherwise.
                     False -> DRF answers 403 automatically.

    DB: one SELECT on accounts_profile via the OneToOne reverse accessor
        (`request.user.profile`). Guard it -- a superuser created with
        createsuperuser has NO Profile row, so `user.profile` raises
        Profile.DoesNotExist. Treat is_superuser as ADMIN.

    USED BY: dispatch/views.py  (commit, zones, responder overrides)
             resources/views.py (PATCH resource, PATCH shelter, supply commit)
             alerts/views.py    (preposition, broadcast)
    """
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        # A superuser made with createsuperuser may predate the Profile signal, so
        # treat staff/superuser as ADMIN rather than 403-ing the person who set the
        # database up.
        if user.is_superuser or user.is_staff:
            return True
        profile = getattr(user, "profile", None)
        return bool(profile and profile.role in (Profile.Role.ADMIN, Profile.Role.OPERATOR))
class IsResponder(BasePermission):
    """Guards the four responder endpoints and guarantees the view can reach
    request.user.profile.resource.

    IN:  request, view
    OUT: bool  -- True when role == "RESPONDER" AND profile.resource_id is not
                  None. A responder with no unit attached cannot answer for one,
                  so returning True there would hand the view a None resource.

    DB: same single SELECT on accounts_profile.

    USED BY: dispatch/views.py ResponderAssignmentView, AssignmentStatusView,
             AssignmentHeadcountView, ResponderLocationView
    """
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        profile = getattr(user, "profile", None)
        # A responder with no unit attached cannot answer for one -- returning True
        # there would hand the view a None resource.
        return bool(profile
                    and profile.role == Profile.Role.RESPONDER
                    and profile.resource_id is not None)
def current_resource(request):
    """The one helper so responder views never re-derive the unit themselves.
    This is why /api/responder/assignment needs no unit id in the URL.

    IN:  request  -- an authenticated DRF Request
    OUT: resources.models.Resource | None

    DB: SELECT ... FROM resources_resource
          JOIN accounts_profile ON profile.resource_id = resource.id
          WHERE profile.user_id = %s
        Use `Profile.objects.select_related("resource").get(user=request.user)`
        so it stays one query.

    NOTE: import Resource lazily or not at all -- accounts must not import
          resources at module level (blueprint 01: never import upward).
          Reaching it through the FK accessor needs no import.
    """
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return None
    try:
        profile = Profile.objects.select_related("resource").get(user=user)
    except Profile.DoesNotExist:
        return None
    return profile.resource