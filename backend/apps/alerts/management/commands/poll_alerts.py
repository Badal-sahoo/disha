"""Fetch the SACHET CAP feed once. Run it on a loop or from cron -- never from
a request, which is why poll_feed() had no caller until this existed.

    python manage.py poll_alerts
"""
from django.core.management.base import BaseCommand

from apps.alerts.services import poll_feed


class Command(BaseCommand):
    help = "Poll the SACHET CAP feed and store any new alerts."

    def handle(self, *args, **options):
        new = poll_feed()
        self.stdout.write(self.style.SUCCESS(f"{len(new)} new alert(s)"))
        for alert in new:
            self.stdout.write(f"  {alert.identifier}  {alert.event} ({alert.severity})")
