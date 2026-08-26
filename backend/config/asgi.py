"""ASGI entry point: HTTP through Django, WebSocket through Channels.

Run with:  daphne -b 127.0.0.1 -p 8000 config.asgi:application
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Django must be set up before importing anything that touches models/settings.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from config.routing import websocket_urlpatterns  # noqa: E402
from realtime.middleware import JWTAuthMiddlewareStack  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # JWTAuthMiddlewareStack reads ?token=<access> off the query string --
        # a browser cannot set an Authorization header on a WS handshake.
        "websocket": JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
