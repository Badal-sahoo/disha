"""Whole websocket + Redis layer, one file.

Job: push live vehicle positions (and the other deltas the map draws) to every
open dashboard.

No auth on the socket -- it is read-only and carries nothing a logged-out user
could act on; all writes go through the REST API, which does check the JWT. That
also means no token in the query string and no reconnect-on-4401 dance.

broadcast() takes plain dicts, never model instances, so every app can import it
without a circular import.
"""
import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from django.conf import settings

log = logging.getLogger(__name__)

GROUP = "ops"


def broadcast(event_type, data):
    """Push one delta to every connected dashboard, via the Redis group layer.

    event_type is one of the strings in frontend/src/shared/utils/constants.js;
    data must be JSON-serialisable.

    Never raises: a dead Redis must not take an API request down. The dashboard
    resyncs through GET /api/state on reconnect, so a dropped delta costs only a
    moment of staleness.
    """
    if not settings.USE_WEBSOCKETS:
        return
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            GROUP, {"type": "ws.event", "event": event_type, "data": data}
        )
    except Exception:
        log.warning("broadcast failed: %s", event_type, exc_info=True)


class OpsConsumer(AsyncJsonWebsocketConsumer):
    """WS /ws/ops -- receive-only. Every message is {"type": ..., "data": ...}."""

    async def connect(self):
        await self.channel_layer.group_add(GROUP, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(GROUP, self.channel_name)

    async def ws_event(self, message):
        # Channel-layer "ws.event" routes here (dot -> underscore).
        await self.send_json({"type": message["event"], "data": message["data"]})
