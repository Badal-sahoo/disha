"""accounts views. Fully wired -- nothing here is a stub.

A view's only job is to check the input, call a service, and return the output.
These three are thin enough that there is no service layer at all.
"""
from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import PS05TokenObtainPairSerializer, ProfileUserSerializer


class LoginView(TokenObtainPairView):
    """POST /api/auth/login

    IN:  {username: str, password: str}
    OUT: 200 {access, refresh, user_id, username, role, resource_id}
         401 {"detail": "No active account found with the given credentials"}
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PS05TokenObtainPairSerializer


class RefreshView(TokenRefreshView):
    """POST /api/auth/refresh

    IN:  {refresh: str}
    OUT: 200 {access: str, refresh: str}   # refresh is rotated (ROTATE_REFRESH_TOKENS)
         401 {"detail": "Token is invalid or expired", "code": "token_not_valid"}

    The axios response interceptor in the frontend calls exactly this endpoint
    on a 401, once, with every other in-flight request queued behind it.
    """
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveAPIView):
    """GET /api/auth/me

    IN:  -- (Authorization: Bearer <access>)
    OUT: 200 {id, username, role, resource_id, resource_code, phone}
         401 when the token is missing or expired
    """
    serializer_class = ProfileUserSerializer

    def get_object(self):
        return self.request.user
