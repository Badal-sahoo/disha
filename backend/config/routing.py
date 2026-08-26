"""WebSocket URL router. Two channels only (system design 07).

  /ws/ops           one broadcast group every dashboard joins
  /ws/unit/{code}   per-team channel, so a rescue crew on a phone is not
                    parsing the whole district's traffic
"""
from django.urls import path

from realtime.consumers import OpsConsumer, UnitConsumer

websocket_urlpatterns = [
    path("ws/ops", OpsConsumer.as_asgi()),
    path("ws/unit/<str:code>", UnitConsumer.as_asgi()),
]
