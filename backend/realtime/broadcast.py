"""The only thing other apps call in here. Fully implemented -- this is
plumbing, not logic.

Takes plain strings and dicts, NEVER model instances. That is the entire reason
realtime needs no import from any other app, and it is what stops dispatch and
realtime importing each other -- the circular-import error every Django project
hits around day 4.
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings

from .events import OPS_GROUP, unit_group

log = logging.getLogger(__name__)


def _send(group, event_type, data):
    """Push one delta onto a channel-layer group.

    IN:  group      = str    # "ops" or "unit_BOAT-04"
         event_type = str    # one of realtime.events.ALL
         data       = dict   # JSON-serialisable. Model instances will NOT work.
    OUT: None

    Never raises. A dead Redis must not take an API request down with it -- the
    dashboard resyncs through GET /api/state on reconnect anyway, so a dropped
    delta costs nothing but a moment of staleness.
    """
    if not settings.USE_WEBSOCKETS:
        return
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            group,
            {"type": "ps05.event", "event_type": event_type, "data": data},
        )
    except Exception:
        log.warning("broadcast failed: %s -> %s", event_type, group, exc_info=True)


def broadcast(event_type, data):
    """Send to the ops group -- every dashboard receives it.

    IN:  event_type = str    # realtime.events.* -- "incident.new", "kpi.update", ...
         data       = dict   # the delta. Same object shape as the matching key
                             #   inside GET /api/state, so the client can apply
                             #   it with the same reducer it uses on a full sync.
    OUT: None

    CALLED BY: reports.services, dispatch.services, resources.services,
               alerts.services, and a few views directly.
    """
    _send(OPS_GROUP, event_type, data)


def notify_unit(code, event_type, data):
    """Send to one team's channel, so a rescue crew on a phone is not parsing
    the whole district's traffic.

    IN:  code       = str    # Resource.code, "BOAT-04"
         event_type = str
         data       = dict
    OUT: None

    Synchronous on purpose. A rescue team must not wait behind a queue of
    citizen alerts.
    """
    _send(unit_group(code), event_type, data)
