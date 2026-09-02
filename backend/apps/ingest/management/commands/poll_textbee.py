"""Pull received SMS from a TextBee gateway phone and feed them to the intake.

    python manage.py poll_textbee --once      # one pass, for testing
    python manage.py poll_textbee             # loop until Ctrl+C

WHY POLL RATHER THAN TAKE THEIR WEBHOOK
---------------------------------------
TextBee will POST a MESSAGE_RECEIVED webhook to a URL you give it, which is the
better design in production. It is useless on a laptop: their cloud has to
reach your server, and this one lives on a LAN address behind NAT. Polling
runs the other way round -- we make the outbound request -- so it works from a
laptop, a hotel wifi, or a demo table, with nothing exposed to the internet.

Switch to the webhook when this is deployed somewhere with a public hostname.
The parsing and dedup below stay exactly the same either way.

SETUP
-----
1. Install the TextBee app on the gateway phone and register it.
2. Turn ON "Receive SMS" in the app -- sending is on by default, receiving is not.
3. Put the API key in backend/.env as TEXTBEE_API_KEY.
"""
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.ingest.services.sms_ingestion import receive_sms

# Only messages that look like they came from the DISHA app are ingested.
#
# This is a privacy guard, not a tidiness one. The gateway phone forwards ALL of
# its incoming SMS to TextBee, so without a filter every OTP, bank alert and
# personal message on that handset would become a row in this database -- and a
# bank alert mentioning "flood relief" would become a pin on the map.
#
# The app always opens its message with HELP (see App/src/sms.ts), so that is
# the handshake. Anything else is left alone.
PREFIX = "help"


def looks_like_a_report(body):
    """IN: str -- OUT: bool. Cheap, deliberately strict."""
    return (body or "").strip().lower().startswith(PREFIX)


class Command(BaseCommand):
    help = "Poll a TextBee gateway for received SMS and turn them into incidents."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true",
                            help="One pass and exit, instead of looping.")
        parser.add_argument("--interval", type=int, default=10,
                            help="Seconds between passes when looping (default 10).")
        parser.add_argument("--lookback", type=int, default=15,
                            help="On the first pass, reach this many minutes back "
                                 "(default 15) so a message sent while this was "
                                 "not running is still picked up.")
        parser.add_argument("--all", action="store_true",
                            help="Ingest every received SMS, not just ones starting "
                                 "with HELP. Forwards personal messages too -- only "
                                 "use it on a dedicated demo SIM.")

    def handle(self, *args, **options):
        api_key = getattr(settings, "TEXTBEE_API_KEY", "")
        if not api_key:
            self.stderr.write(self.style.ERROR(
                "TEXTBEE_API_KEY is not set. Add it to backend/.env."))
            return

        base = getattr(settings, "TEXTBEE_BASE_URL", "https://api.textbee.dev")
        url = f"{base.rstrip('/')}/api/v1/gateway/messages"
        session = requests.Session()
        session.headers["x-api-key"] = api_key

        # Their API takes a `from` timestamp, so we ask only for what is new.
        # receive_sms() also dedups on (gateway_id, received_at, from_number),
        # which is the real safety net -- an overlapping window cannot double up.
        since = timezone.now() - timedelta(minutes=options["lookback"])
        self.stdout.write(f"polling {url} every {options['interval']}s "
                          f"(filter: {'none' if options['all'] else 'HELP prefix'})")

        while True:
            try:
                since = self._pass(session, url, since, options["all"])
            except requests.RequestException as exc:
                # A dropped connection must not kill the poller mid-demo.
                self.stderr.write(self.style.WARNING(f"  textbee unreachable: {exc}"))

            if options["once"]:
                return
            time.sleep(options["interval"])

    def _pass(self, session, url, since, ingest_all):
        """One fetch. Returns the timestamp to ask from next time."""
        response = session.get(
            url,
            params={"direction": "received", "order": "asc",
                    "from": since.isoformat()},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()

        # Their responses have been seen both as a bare list and wrapped in
        # {data: [...]}, so cope with either rather than crash on a shape change.
        messages = payload.get("data", payload) if isinstance(payload, dict) else payload
        if not isinstance(messages, list):
            self.stderr.write(self.style.WARNING(f"  unexpected body: {str(payload)[:120]}"))
            return since

        newest = since
        for message in messages:
            body = message.get("message") or message.get("body") or ""
            sender = (message.get("sender") or message.get("from")
                      or message.get("phoneNumber") or "")
            stamp = (parse_datetime(str(message.get("receivedAt")
                                        or message.get("createdAt") or ""))
                     or timezone.now())
            if timezone.is_naive(stamp):
                stamp = timezone.make_aware(stamp)
            newest = max(newest, stamp)

            if not ingest_all and not looks_like_a_report(body):
                continue

            result = receive_sms(
                from_number=sender,
                body=body,
                received_at=stamp,
                # TextBee's own id, so a repeated poll cannot create a second row.
                gateway_id=str(message.get("_id") or message.get("id") or ""),
            )
            if result["code"]:
                self.stdout.write(self.style.SUCCESS(
                    f"  {result['code']}  {sender}  \"{body[:48]}\""))
            else:
                self.stdout.write(
                    f"  triage   {sender}  \"{body[:48]}\"  (no location)")

        return newest
