"""accounts views: check the input, issue or read a token. Thin enough that
there is no service layer at all."""
from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import PS05TokenObtainPairSerializer, ProfileUserSerializer


class LoginView(TokenObtainPairView):
    """POST /api/auth/login {username, password}
    -> 200 {access, refresh, user_id, username, role, resource_id}   401 otherwise
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PS05TokenObtainPairSerializer


class RefreshView(TokenRefreshView):
    """POST /api/auth/refresh {refresh} -> 200 {access, refresh}

    The refresh token is rotated (ROTATE_REFRESH_TOKENS), so it is valid exactly
    once -- which is why the frontend's axios interceptor refreshes single-flight.
    """
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveAPIView):
    """GET /api/auth/me -> the caller's identity, 401 without a valid token."""
    serializer_class = ProfileUserSerializer

    def get_object(self):
        return self.request.user
