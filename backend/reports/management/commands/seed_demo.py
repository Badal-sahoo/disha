"""Load the Odisha cyclone demo scenario.

The day-1 milestone from the build plan: migrations run, this script loads the
scenario, and GET /api/state returns it. Everything after that is presentation.

    python manage.py seed_demo --reset
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed the Odisha cyclone demo scenario (users, units, shelters, depots)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Delete existing demo rows before seeding.")
        parser.add_argument("--incidents", type=int, default=0,
                            help="Also create N random open incidents.")

    def handle(self, *args, **options):
        """
        IN:  --reset      bool   wipe first
             --incidents  int    how many synthetic open incidents to create
        OUT: prints a summary; writes rows.

        WHAT TO CREATE (numbers match the benchmark in ps05/code/allocation/simulator.py):
          accounts   1 ADMIN, 2 OPERATOR, and one RESPONDER per rescue unit,
                     each Profile.resource pointing at the unit they drive.
                     Password "demo1234" for all of them -- this is a seed
                     script for a laptop, not a fixture for production.
          resources  ~28 Resource rows around Puri/Konark (19.7-20.0 N, 85.7-86.1 E):
                       12 BOAT      capabilities ["BOAT","ROPE_RESCUE"]   capacity 12  speed 18
                        8 TEAM      ["ROPE_RESCUE","MEDICAL"]            capacity 6   speed 25
                        4 TRUCK     ["HIGH_CLEARANCE","SUPPLY"]          capacity 30  speed 35
                        4 AMBULANCE ["MEDICAL"]                          capacity 4   speed 45
                     capabilities MUST match dispatch.engine.REQUIRED_CAPS or
                     is_capable() rejects every pairing and the solve returns [].
          shelters   ~10 Shelter rows, capacity 150-600, occupancy 0
          depots     3 Depot rows, each with SupplyStock for all four items
          zones      2 Zone rows (severity 5 and severity 3) so the road-cut
                     story has something to show on first load

        DB: one transaction.atomic() for the whole seed. With --reset, delete in
            FK order: Assignment, Incident, SupplyStock, Depot, Shelter,
            Profile, Resource -- Assignment protects Resource
            (on_delete=PROTECT), so units cannot be deleted first.

        USES: common.codes.next_code for the code columns, or hardcode
              "BOAT-01".."BOAT-12" style codes here -- readable codes make the
              demo easier to narrate than INC0142 sequences.
        """
        raise NotImplementedError("seed_demo -- Track 5 - Day 1")
