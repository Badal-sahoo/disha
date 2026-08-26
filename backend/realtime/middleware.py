"""JWT auth for WebSockets. Fully implemented.

A browser cannot set an Authorization header on a WebSocket handshake -- the
WebSocket API simply has no place to put one. So the access token rides in the
query string instead: /ws/ops?token=<access>. This middleware validates it and
puts the resulting user on scope["user"], which is all the consumers need.

The token is short-lived (60 minutes) and the connection is wss:// in
production. On a 4401 close the frontend refreshes and reconnects, which is
already wired in shared/api/socket.js.
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _user_from_token(raw_token):
    """Resolve an access token to a User.

    IN:  raw_token = str      # the JWT from ?token=
    OUT: User | AnonymousUser # AnonymousUser on any failure -- expired,
                              #   malformed, blacklisted, or user deleted

    DB: one SELECT on auth_user by the token's user_id claim.
    """
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    try:
        token = AccessToken(raw_token)
        return get_user_model().objects.select_related("profile").get(
            pk=token["user_id"]
        )
    except (TokenError, KeyError, get_user_model().DoesNotExist):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """Reads ?token= off the handshake URL and sets scope["user"]."""

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        raw_token = (query.get("token") or [None])[0]
        scope["user"] = await _user_from_token(raw_token) if raw_token else AnonymousUser()
        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    """What config/asgi.py wraps the websocket URLRouter in."""
    return JWTAuthMiddleware(inner)
