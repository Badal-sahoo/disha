"""accounts serializers -- JWT issue + the identity payload."""
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Profile

User = get_user_model()


class ProfileUserSerializer(serializers.ModelSerializer):
    """GET /api/auth/me

    OUT: {
      id:          int,
      username:    str,
      role:        str,        # "ADMIN" | "OPERATOR" | "RESPONDER"
      resource_id: int|None,   # PK of resources.Resource this person drives
      resource_code: str|None, # "BOAT-04" -- convenience for the responder app
      phone:       str,        # may be ""
    }
    """
    role = serializers.CharField(source="profile.role", read_only=True)
    resource_id = serializers.IntegerField(source="profile.resource_id", read_only=True)
    resource_code = serializers.CharField(source="profile.resource.code", read_only=True, default=None)
    phone = serializers.CharField(source="profile.phone", read_only=True, default="")

    class Meta:
        model = User
        fields = ["id", "username", "role", "resource_id", "resource_code", "phone"]


class PS05TokenObtainPairSerializer(TokenObtainPairSerializer):
    """POST /api/auth/login

    IN:  {username: str, password: str}
    OUT: {
      access:      str,        # JWT, 60 min. Frontend puts this in the Bearer header.
      refresh:     str,        # JWT, 7 days. Rotated on every refresh.
      user_id:     int,
      username:    str,
      role:        str,        # "ADMIN" | "OPERATOR" | "RESPONDER"
      resource_id: int|None,
    }

    role and resource_id ride along in BOTH the response body (so the React app
    can gate routes on first paint without a second call) and the access-token
    claims (so realtime/middleware.py can authorise a WebSocket without a DB hit).
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        profile = getattr(user, "profile", None)
        token["role"] = getattr(profile, "role", Profile.Role.OPERATOR)
        token["resource_id"] = getattr(profile, "resource_id", None)
        token["username"] = user.username
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        profile = getattr(self.user, "profile", None)
        data["user_id"] = self.user.id
        data["username"] = self.user.username
        data["role"] = getattr(profile, "role", Profile.Role.OPERATOR)
        data["resource_id"] = getattr(profile, "resource_id", None)
        return data
