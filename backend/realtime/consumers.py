"""Two consumers, mostly boilerplate from the Channels docs. Fully implemented.

Both are receive-only from the server's point of view: clients do not send
commands over the socket, they call REST endpoints. That keeps authorisation in
one place and the socket dumb.
"""
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .events import OPS_GROUP, unit_group


class OpsConsumer(AsyncJsonWebsocketConsumer):
    """WS /ws/ops?token=<access JWT>

    One broadcast group every dashboard joins. Receives all ten event types.

    OUT (every message pushed to the client):
      {type: str, data: obj, }   # type is one of realtime.events.ALL

    AUTH: realtime.middleware.JWTAuthMiddleware has already put a user on
    scope["user"] from the ?token= query parameter. An anonymous socket is
    closed with 4401 -- a custom code so the frontend can tell "your token
    expired, refresh and reconnect" apart from a network drop.
    """
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        await self.channel_layer.group_add(OPS_GROUP, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected", "data": {"group": OPS_GROUP}})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(OPS_GROUP, self.channel_name)

    async def ps05_event(self, message):
        """Channel-layer handler. The dotted "ps05.event" type sent by
        broadcast() maps to this underscored method name -- that renaming is a
        Channels convention, not a typo."""
        await self.send_json({"type": message["event_type"], "data": message["data"]})


class UnitConsumer(AsyncJsonWebsocketConsumer):
    """WS /ws/unit/{code}?token=<access JWT>

    Per-team channel. A new assignment arrives as a push, not a poll -- a team
    should not have to pull-to-refresh during a rescue.

    OUT: {type: "assignment.new"|"assignment.update"|"zone.new"|"zone.removed",
          data: obj}

    AUTH: closes with 4401 when unauthenticated, and 4403 when the token's
    resource_id does not match the {code} in the URL. Without that second check
    any logged-in user could listen to any team's traffic.
    """
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.code = self.scope["url_route"]["kwargs"]["code"]
        if not await self._owns_unit(user, self.code):
            await self.close(code=4403)
            return

        self.group = unit_group(self.code)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected", "data": {"group": self.group}})

    async def disconnect(self, code):
        group = getattr(self, "group", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def ps05_event(self, message):
        await self.send_json({"type": message["event_type"], "data": message["data"]})

    @staticmethod
    async def _owns_unit(user, code):
        """True when this user drives this unit, or is staff.

        IN:  user = django User (already authenticated)
             code = str          # Resource.code from the URL
        OUT: bool

        DB: one SELECT joining accounts_profile -> resources_resource, wrapped in
            database_sync_to_async because we are in async context.
        """
        from channels.db import database_sync_to_async

        @database_sync_to_async
        def _check():
            if user.is_staff or user.is_superuser:
                return True
            profile = getattr(user, "profile", None)
            resource = getattr(profile, "resource", None)
            return bool(resource and resource.code == code)

        return await _check()
