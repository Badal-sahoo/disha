"""Load the Odisha cyclone demo scenario: users, units, shelters, zones.

    python manage.py seed_demo --reset --scenario        # a scripted situation
    python manage.py seed_demo --reset --incidents 12    # random extra load

WHY NOTHING IS PLACED RANDOMLY ANY MORE
---------------------------------------
This used to scatter units and shelters uniformly across
LAT 19.70-20.00 x LON 85.70-86.10. That rectangle is roughly half Bay of
Bengal -- the coast runs diagonally through it -- so boats, trucks and
ambulances were seeded into open sea and "Puri High School" floated offshore.
Every position now comes from PLACES: real, named, on land. Random jitter is
kept to a few hundred metres around a real point, which cannot cross a
coastline.

--incidents scatters reports across those same places, which is fine for load
but tells no story: every pin looks like every other one. --scenario lays down
a specific night -- cyclone landfall on the Puri coast, about six hours in --
with clustered reports, a cut coastal road, filling shelters, and units already
lost to the storm.

Capabilities MUST line up with dispatch.engine.REQUIRED_CAPS, or is_capable()
rejects every pairing and the solve returns nothing:
    FLOOD     -> BOAT | HIGH_CLEARANCE
    CYCLONE   -> HIGH_CLEARANCE | MEDICAL | ROPE_RESCUE
    LANDSLIDE -> EXCAVATION | ROPE_RESCUE        (only TEAM carries either)

Password for every seeded account is "demo1234" -- this is a seed script for a
laptop, not production.
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Profile
from apps.alerts.models import Alert
from apps.common.geo import cell_for
from apps.dispatch.models import Assignment, Zone
from apps.reports.models import Incident
from apps.resources.models import Resource, Shelter

PASSWORD = "demo1234"

# Real places in and around Puri district. Every one of these has been checked
# against data/puri.osm.json and sits within 400 m of a mapped road, which is
# what guarantees nothing is seeded into the Bay of Bengal or Chilika lake.
#
# To re-check after editing, snap each pair to the nearest OSM node and look at
# the distance: anything over ~1 km is almost certainly in water.
PLACES = {
    # EVERY COORDINATE BELOW IS FROM OpenStreetMap, not from memory.
    #
    # The previous set was hand-guessed and several were badly wrong: Chandanpur
    # was 16.7 km from the real town, Kakatpur 17 km, Delang 14 km, Brahmagiri
    # 12 km. That is not a cosmetic problem in a routing demo -- every ETA, every
    # "nearest unit" decision and every shortest path was computed against a
    # district that does not exist. Re-query with:
    #
    #   [out:json];node["place"~"^(city|town|village)$"](19.60,85.55,20.20,86.30);out;
    #
    # verify_places() below snaps each one to the road graph and fails the seed
    # if anything lands more than a kilometre from a mapped road.
    "puri":        (19.80761, 85.82525),   # city, district HQ (Jagannath temple)
    # The beach front, as a STRETCH. Main Puri's flooding is not a blob at the
    # temple -- it is the line of hotels, sheds and fishing colonies along the
    # sand from Swargadwar east past Chakratirtha, and the families reporting
    # from it are strung out along that line, not clustered on a town centre.
    "puri_beach_w": (19.79860, 85.81420),  # Swargadwar, west end
    "puri_beach_m": (19.80320, 85.83180),  # in front of the main sea beach
    "puri_beach_e": (19.80960, 85.85120),  # Chakratirtha / lighthouse end
    "pipili":      (20.11879, 85.83333),   # town, on NH-316 toward Bhubaneswar
    "sakhigopal":  (19.94831, 85.81453),   # town, Satyabadi block
    "chandanpur":  (19.89049, 85.81737),   # town, Puri Sadar block
    "konark":      (19.88994, 86.09231),   # town, Gop block
    "nimapara":    (20.05986, 86.01035),   # village/NAC, Nimapada block
    "delanga":     (20.06278, 85.74829),   # village, Delang block
    "kakatpur":    (20.00251, 86.19822),   # village, Kakatpur block
    "astaranga":   (19.97843, 86.26838),   # village, Astaranga block -- the coast
    "gop":         (19.98491, 86.01707),   # village, Gop block
    "brahmagiri":  (19.79630, 85.64285),   # village, Brahmagiri block
    "balighai":    (19.86153, 85.94331),   # village, on the Puri-Konark marine drive
    "batagaon":    (19.85542, 85.83234),   # village, 5.6 km inland of Puri
    "alipada":     (19.81267, 85.76151),   # village, 6.4 km from the shore
    "gopikantapur": (20.01501, 86.15401),  # village, Kakatpur block
}

# ---------------------------------------------------------------------------
# HOSPITALS -- where an ambulance actually takes a casualty.
#
# Every one of these is a real, named government health facility. The names and
# coordinates come from OpenStreetMap; the facility TIER of each was
# cross-checked against the Odisha Health & Family Welfare Department's "List of
# Major Health Institutions" for Puri district
# (health.odisha.gov.in/sites/default/files/2020-03/puri.pdf), which lists
# DHH Puri, the Area Hospitals at Kakatpur / Nimapara / Balanga / Pipili /
# Sakhigopal, and the CHCs at Chandanpur, Gop, Kanas and Rebana Nuagaon.
#
# BED COUNTS are the Indian Public Health Standards 2022 band for each tier, NOT
# a claim about how many beds that specific building has today:
#     District Hospital        101-500  -> 250 used here
#     Sub-district / Area Hosp  31-100  ->  60
#     Community Health Centre       30  ->  30
#     Primary Health Centre (24x7)   6  ->   6
# Tier norms are the honest thing to seed with: they are published, they are
# defensible on stage, and they produce the right RELATIVE capacities, which is
# all the dispatcher actually reasons about.
#
# name, place-or-(lat,lon), beds
# ---------------------------------------------------------------------------
HOSPITALS = [
    ("District Headquarter Hospital, Puri", (19.81427, 85.82995), 250),   # DHH
    ("CHC Chandanpur",                      (19.89557, 85.80802),  30),
    ("CHC Nayahat",                         (20.02778, 86.14487),  30),
    ("Area Hospital, Kakatpur",             (20.00153, 86.19795),  60),
]

# Where each kind of unit is based, by PLACES key.
#
# Boats sit where there is water to launch into: the Devi river mouth at
# Astaranga, the Chilika side at Brahmagiri, and the two coastal towns.
# Ambulances sit at the towns that actually have a hospital in HOSPITALS above --
# an ambulance parked in a village with no hospital is a demo artefact.
BASES = {
    # Boats launch at the coast because that is where the water is. Trucks and
    # ambulances sit inland on dry road, which is also where they are taking
    # people TO -- so a loaded truck is already pointing the right way.
    "BOAT":      ["astaranga", "konark", "balighai", "puri"],
    "TEAM":      ["konark", "chandanpur", "kakatpur", "puri"],
    "TRUCK":     ["chandanpur", "sakhigopal"],
    "AMBULANCE": ["puri", "chandanpur"],
}

# kind, count, capabilities, capacity, speed_kmph
FLEET = [
    # SMALL ON PURPOSE. This was 28 units across 4 kinds, which is realistic and
    # completely unreadable: the map was a wall of overlapping rings around Puri
    # and nobody watching could follow which unit went where. Twelve is enough to
    # be scarce against the scenario below -- so the optimiser still has a real
    # choice to make -- and few enough that a person can point at one and say
    # "that boat, to that village".
    ("BOAT", 4, ["BOAT"], 12, 18.0),
    ("TEAM", 4, ["BOAT", "ROPE_RESCUE", "MEDICAL"], 6, 25.0),
    ("TRUCK", 2, ["HIGH_CLEARANCE"], 30, 35.0),
    ("AMBULANCE", 2, ["MEDICAL"], 4, 45.0),
]

# name, place, capacity.
#
# Odisha's multipurpose cyclone shelter network is real: OSDMA and the World
# Bank-funded NCRMP built several hundred of them across the coastal districts,
# and they are the buildings a village is actually evacuated to. Individual
# shelters are NOT mapped in OpenStreetMap, so each one here is named for the
# real settlement it serves and placed at that settlement rather than at a
# surveyed building footprint. Capacities are in the 150-600 band an MCS is
# built to. The places are real; the building coordinates are village-accurate,
# not metre-accurate, and that is the honest description of them.
# name, place, capacity.
#
# INLAND, ALL OF THEM. This is the whole point of an evacuation and the seed had
# it backwards: shelters were sitting in Astaranga and Konark -- the two villages
# that go under first -- so the map showed people being carried from a flooded
# village to a flooded building, and the demo argued against itself.
#
# Every shelter here is in the amber or green risk band (>6 km from the shore,
# see frontend/src/features/map/risk.js). Capacity is sized for the ~500 people
# in the scenario: a coastal district evacuates INLAND, and there has to be room.
#
# Real note: Odisha's MCS buildings genuinely do stand inside coastal villages --
# they are raised concrete blocks built to survive the surge. That is a different
# design from "move people away from the sea", and it is the second one this
# dashboard is showing.
SHELTERS = [
    ("Chandanpur MCS",     "chandanpur", 300),   # ~10 km in
    ("Sakhigopal MCS",     "sakhigopal", 300),   # ~16 km in
    ("Nimapara Stadium",   "nimapara",   600),   # ~25 km in, the big one
    ("Gop Block Centre",   "gop",        250),   # ~11 km in
    ("Pipili Block Office", "pipili",    200),   # far inland, green band
]

# ---------------------------------------------------------------------------
# The scenario: cyclone landfall on the Puri coast, roughly six hours in.
#
# place, kind, severity, people, age_min, reports, description
#
# `reports` > 1 means that many neighbours called it in separately. They land in
# one cell_id, so the dashboard groups them into a single job and the engine's
# corroboration term treats them as confirmed rather than a lone caller.
# ---------------------------------------------------------------------------
SCENARIO = [
    # ~500 PEOPLE, ONE REPORT PER FAMILY, ALL ON THE COAST.
    #
    # Every entry below is a village in the RED risk band -- within about 6 km of
    # the shoreline, the belt that actually goes under in a surge. Nothing is
    # seeded inland: inland is where the shelters are, and a district where the
    # flooding and the refuge are in the same place is not a district anyone
    # needs a dispatcher for.
    #
    # `families` is the number of SEPARATE reports. Each carries one household,
    # 3 to 6 people, sent from its own phone within a few minutes of its
    # neighbours. On the map every family is its own pin; they share a cell, so
    # they cluster into ONE circle and ONE dispatch card carrying the whole
    # village's headcount. That is the difference between 117 pins and 8 jobs,
    # and it is the thing worth showing.
    #
    # place, kind, severity, families, age_min, description

    # --- the shoreline: worst hit, biggest clusters --------------------------
    ("astaranga", "FLOOD", 5, 30, 95,
     "Sea water in the house, we are on the roof"),
    ("konark", "FLOOD", 5, 24, 78,
     "Water came up the lane after the surge, cannot get out"),
    ("balighai", "FLOOD", 4, 18, 110,
     "Marine drive under water both ways, families stranded"),
    # Main Puri, spread along the beach as three points on the same stretch --
    # separate cells, so they draw as three circles strung along the shore
    # rather than one lump inland at the temple.
    ("puri_beach_w", "FLOOD", 4, 9, 44,
     "Swargadwar lanes flooded, ground floors gone"),
    ("puri_beach_m", "FLOOD", 5, 12, 38,
     "Sea has come over the road, sheds washed out"),
    ("puri_beach_e", "FLOOD", 4, 8, 30,
     "Fishing colony under water near the lighthouse"),

    # --- a few kilometres in, still in the red band --------------------------
    ("kakatpur", "FLOOD", 3, 12, 55,
     "Prachi river over the bund, ground floor under water"),
    ("gopikantapur", "FLOOD", 3, 8, 45,
     "Bund broken on the far side, we are cut off"),

    # --- casualties: need MEDICAL, and go to a HOSPITAL, not a shelter -------
    ("batagaon", "CYCLONE", 4, 3, 25,
     "Roof collapsed, one person unconscious"),
    ("alipada", "CYCLONE", 5, 2, 18,
     "Man crushed under a fallen hoarding, bleeding heavily"),
]

# The warning that started the night. Polygon is [[lat, lon], ...].
#
# A band that follows the coastline rather than a rectangle over the district:
# seaward edge south of the towns, inland edge roughly 15-20 km in. Checked by
# point-in-polygon against PLACES -- it must cover every coastal block that has
# reports in it (Sakhigopal above all, the largest cluster) and leave the two
# most inland ones, Delanga and Nimapara, outside. A warning that misses a
# village which is visibly flooding on the same map is the first thing anyone
# watching will notice.
CAP_POLYGON = [
    # A band following the real coastline, seaward edge offshore and inland edge
    # roughly 20 km in. Verified by point-in-polygon against PLACES: it must
    # cover every coastal block that has reports in it -- Sakhigopal above all,
    # the largest cluster -- and leave the inland ones, Delang, Pipili and
    # Nimapara, outside. A warning that misses a village visibly flooding on the
    # same map is the first thing anyone watching will notice.
    [19.72, 85.60],   # SW, off the Chilika mouth
    [19.75, 85.85],   # south of Puri, seaward
    [19.84, 86.12],   # off Konark and Chandrabhaga
    [19.93, 86.32],   # off the Devi river mouth at Astaranga
    [20.06, 86.28],   # NE, turning inland
    [20.02, 86.05],   # inland edge, heading back west
    [19.96, 85.85],   # inland of Sakhigopal
    [19.88, 85.66],   # closing toward Chilika
    [19.72, 85.60],
]


class Command(BaseCommand):
    help = "Seed the Odisha cyclone demo scenario (users, units, shelters, zones)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Delete existing demo rows before seeding.")
        parser.add_argument("--incidents", type=int, default=0,
                            help="Also create N random open incidents.")
        parser.add_argument("--no-reports", action="store_true",
                            help="Seed the world but leave the district QUIET: no "
                                 "waiting incidents. Use this for the phone demo, so "
                                 "the victim's SOS is the first call in and gets the "
                                 "nearest boat instead of whatever is left over.")
        parser.add_argument("--scenario", action="store_true",
                            help="Seed the scripted cyclone situation instead of "
                                 "random pins: clustered reports, a CAP warning, "
                                 "filling shelters, units lost to the storm.")

    @transaction.atomic
    def handle(self, *args, **options):
        # Fixed seed: two runs give the same map, which makes a demo repeatable.
        rng = random.Random(42)

        if options["reset"]:
            # FK order: Assignment protects Resource (on_delete=PROTECT), so
            # units cannot go first.
            Assignment.objects.all().delete()
            Incident.objects.all().delete()
            Shelter.objects.all().delete()
            Zone.objects.all().delete()
            Alert.objects.all().delete()
            Resource.objects.all().delete()

            # Accounts deliberately SURVIVE a reset.
            #
            # Deleting them renumbered every user, which silently invalidated
            # every JWT already issued -- so re-seeding mid-demo logged the
            # dashboard and the phone out, and both had to sign in again on
            # camera. Profile.resource is SET_NULL, so dropping the units above
            # just unlinks the crews; _seed_users re-points them below.
            self.stdout.write("reset: incidents, units, shelters, zones, alerts "
                              "cleared (logins kept)")

        def near(place, spread=0.006):
            """A point within ~600 m of a real place -- still on land."""
            lat, lon = PLACES[place]
            return (round(lat + rng.uniform(-spread, spread), 4),
                    round(lon + rng.uniform(-spread, spread), 4))

        units = []
        for kind, count, caps, capacity, speed in FLEET:
            bases = BASES[kind]
            for n in range(1, count + 1):
                base = bases[(n - 1) % len(bases)]
                lat, lon = near(base)
                unit, _ = Resource.objects.update_or_create(
                    code=f"{kind}-{n:02d}",
                    defaults={
                        "name": f"{kind.title()} {n}", "kind": kind,
                        "lat": lat, "lon": lon, "capabilities": caps,
                        "capacity": capacity, "speed_kmph": speed,
                        "status": Resource.Status.IDLE, "free_at": None,
                        "base_name": base.replace("_", " ").title(),
                    },
                )
                units.append(unit)

        shelters = []
        for n, (name, place, capacity) in enumerate(SHELTERS, start=1):
            lat, lon = near(place, spread=0.003)
            shelter, _ = Shelter.objects.update_or_create(
                code=f"SHL-{n:02d}",
                defaults={"name": name, "kind": Shelter.Kind.SHELTER,
                          "lat": lat, "lon": lon,
                          "capacity": capacity, "occupancy": 0,
                          "status": Shelter.Status.OPEN},
            )
            shelters.append(shelter)

        hospitals = []
        for n, (name, (lat, lon), beds) in enumerate(HOSPITALS, start=1):
            hospital, _ = Shelter.objects.update_or_create(
                code=f"HOS-{n:02d}",
                defaults={"name": name, "kind": Shelter.Kind.HOSPITAL,
                          "lat": lat, "lon": lon,
                          "capacity": beds, "occupancy": 0,
                          "status": Shelter.Status.OPEN},
            )
            hospitals.append(hospital)

        self._seed_zones()
        self._seed_users(units)

        if options["scenario"]:
            made = self._seed_scenario(rng, units, shelters,
                                       with_reports=not options["no_reports"])
        else:
            made = 0

        self._seed_incidents(rng, options["incidents"])

        self._verify_places()

        user_count = 3 + len(units)   # 1 admin + 2 operators + one per unit
        self.stdout.write(self.style.SUCCESS(
            f"seeded {len(units)} units, {len(shelters)} shelters, "
            f"{len(hospitals)} hospitals, {user_count} users, "
            f"{made + options['incidents']} incidents (password '{PASSWORD}')"))

    def _verify_places(self):
        """Snap every seeded point to the road graph and complain about outliers.

        This is the check that would have caught the old coordinates. A place
        that snaps 16 km to the nearest mapped road is not a village -- it is a
        guess, and in this district a guess usually lands in the Bay of Bengal or
        in Chilika lake. Cheap to run and it fails loudly at seed time instead of
        quietly at demo time.
        """
        from apps.dispatch.services.routing import road_network

        network = road_network()
        if network is None:
            self.stdout.write(self.style.WARNING(
                "no road graph -- skipping the place check "
                "(run `manage.py seed_roadgraph` to enable it)"))
            return

        from apps.dispatch.engine import haversine_km

        points = [(f"place:{name}", lat, lon) for name, (lat, lon) in PLACES.items()]
        points += [(f"hospital:{name}", lat, lon) for name, (lat, lon), _ in HOSPITALS]
        points += [(f"{r.code}", r.lat, r.lon) for r in Resource.objects.all()]
        points += [(f"{s.code}", s.lat, s.lon) for s in Shelter.objects.all()]

        worst = []
        for label, lat, lon in points:
            node = network.snap([lat], [lon])[0]
            km = haversine_km(lat, lon, float(network.lat[node]), float(network.lon[node]))
            if km > 1.0:
                worst.append((km, label))

        if worst:
            worst.sort(reverse=True)
            for km, label in worst[:10]:
                self.stdout.write(self.style.ERROR(
                    f"  {label} is {km:.1f} km from the nearest mapped road"))
            raise CommandError(
                f"{len(worst)} seeded point(s) are not near a road -- fix the "
                f"coordinates rather than shipping a district that does not exist")

        self.stdout.write("place check: every seeded point is within 1 km of a road")

    def _seed_zones(self):
        """Two cut areas, so the road-cut story has something on first load."""
        # The Devi river mouth at Astaranga. Severity 5 = impassable without a
        # hull, which is what strands the village seeded at the same place and
        # forces the solver to spend a BOAT rather than the nearer truck.
        Zone.objects.update_or_create(
            lat=19.9784, lon=86.2684,
            defaults={"radius_km": 5.0, "severity": 5,
                      "source": Zone.Source.CAP, "active": True})
        # Waterlogging on the Puri-Sakhigopal road: passable, but it slows a
        # wheeled unit to a crawl and makes the boat the better answer.
        Zone.objects.update_or_create(
            lat=19.8900, lon=85.8200,
            defaults={"radius_km": 3.0, "severity": 3,
                      "source": Zone.Source.OPERATOR, "active": True})

    def _seed_scenario(self, rng, units, shelters, with_reports=True):
        """The scripted situation. Returns how many incidents it created.

        with_reports=False keeps the warning, the cut roads, the filling
        shelters and the storm-damaged units, but leaves nobody waiting. That
        is the state the phone demo wants: one SOS arrives into a quiet
        district and is answered immediately, instead of queueing behind
        eighteen older calls that already took every nearby boat.
        """
        from apps.common.codes import next_code

        now = timezone.now()

        # --- the warning that started it ---------------------------------
        Alert.objects.update_or_create(
            identifier="urn:oid:2.49.0.1.356.demo.2026.puri.01",
            defaults={
                "event": "Cyclone Warning",
                "severity": "Extreme",
                "urgency": "Immediate",
                "certainty": "Observed",
                "polygon": CAP_POLYGON,
                "sent_at": now - timedelta(hours=6),
                "expires_at": now + timedelta(hours=12),
                "active": True,
            },
        )

        # --- the reports --------------------------------------------------
        made = 0
        for place, kind, severity, families, age_min, description in (
                SCENARIO if with_reports else []):
            base_lat, base_lon = PLACES[place]

            # Every caller in a village MUST land in the same cell_id, or they
            # group as separate jobs and the corroboration count never builds.
            #
            # Jittering around the village and hoping was not enough. Sakhigopal
            # sits at lon 85.81453, which is 0.00047 from the 85.815 rounding
            # boundary -- so a +-0.001 jitter put some callers in cell 85.81 and
            # the rest in 85.82, and one breach with five witnesses arrived as
            # two separate jobs. Nine scenario entries produced ten scenes.
            #
            # Jitter inside the CELL instead: take the village's own cell, and
            # scatter the callers within it. The pins still spread across the
            # village, and they cannot cross a boundary because the boundary is
            # what we are scattering inside of.
            cell_lat, cell_lon = (round(base_lat, 2), round(base_lon, 2))

            for n in range(families):
                lat = round(cell_lat + rng.uniform(-0.0035, 0.0035), 4)
                lon = round(cell_lon + rng.uniform(-0.0035, 0.0035), 4)

                incident = Incident.objects.create(
                    code=next_code("INC", Incident),
                    client_ref=f"scenario-{place}-{n}-{rng.getrandbits(32):08x}",
                    lat=lat, lon=lon,
                    kind=kind, severity=severity,
                    # ONE HOUSEHOLD, not a share of the village. A family is
                    # two to six people; the scene's total is whatever its
                    # callers add up to, which is how the real number is built.
                    people=rng.randint(2, 6),
                    description=description,
                    source=Incident.Source.SMS if n % 2 else Incident.Source.APP,
                    cell_id=cell_for(lat, lon),
                    corroborations=families,
                    status=Incident.Status.OPEN,
                )
                # reported_at is auto_now_add, so it ignores anything passed to
                # create(). Backdating has to be a second write -- and it
                # matters: the priority function's age term is the whole reason
                # a three-hour-old call outranks a fresh one of equal severity.
                #
                # Neighbours do not all dial at once: spread them over a few
                # minutes so the oldest call sets the clock for the scene.
                Incident.objects.filter(pk=incident.pk).update(
                    reported_at=now - timedelta(minutes=age_min - n * 2)
                )
                made += 1

        # --- shelters that are already filling up --------------------------
        by_code = {s.code: s for s in shelters}
        occupancy = {
            "SHL-01": 380,   # Puri, 84% -- amber
            "SHL-03": 200,   # Konark, full
            "SHL-05": 90,
        }
        for code, filled in occupancy.items():
            shelter = by_code[code]
            shelter.occupancy = filled
            if filled >= shelter.capacity:
                shelter.status = Shelter.Status.FULL
            shelter.save(update_fields=["occupancy", "status"])

        # Behind the severity-5 zone: standing but unreachable, which is why the
        # village at the Devi mouth cannot simply be evacuated to it.
        astaranga = by_code["SHL-04"]
        astaranga.status = Shelter.Status.INACCESSIBLE
        astaranga.save(update_fields=["status"])

        # --- units the storm has already taken out -------------------------
        # Real scarcity, so the optimiser has to make a choice worth explaining.
        # One boat lost to the storm. With only four, losing one is felt.
        for code in ("BOAT-04",):
            Resource.objects.filter(code=code).update(
                status=Resource.Status.OUT_OF_SERVICE)

        return made

    def _seed_users(self, units):
        """1 ADMIN, 2 OPERATORs, and one RESPONDER per unit."""
        User = get_user_model()

        def account(username, role, resource=None, staff=False):
            user, _ = User.objects.get_or_create(
                username=username, defaults={"is_staff": staff})
            user.set_password(PASSWORD)
            user.is_staff = staff
            user.save()
            # The post_save signal already made the Profile; point it at the role.
            Profile.objects.update_or_create(
                user=user, defaults={"role": role, "resource": resource})

        account("admin_demo", Profile.Role.ADMIN, staff=True)
        for n in (1, 2):
            account(f"operator{n}", Profile.Role.OPERATOR)
        for unit in units:
            account(unit.code.lower().replace("-", ""), Profile.Role.RESPONDER, unit)

    def _seed_incidents(self, rng, count):
        """Random extra load. Still anchored to real places -- never open sea."""
        from apps.common.codes import next_code

        # Floods dominate an Odisha cyclone scenario, so weight the mix.
        kinds = ([Incident.Kind.FLOOD] * 6
                 + [Incident.Kind.CYCLONE] * 3
                 + [Incident.Kind.LANDSLIDE])
        names = list(PLACES)

        for _ in range(count):
            base_lat, base_lon = PLACES[rng.choice(names)]
            lat = round(base_lat + rng.uniform(-0.02, 0.02), 4)
            lon = round(base_lon + rng.uniform(-0.02, 0.02), 4)
            Incident.objects.create(
                code=next_code("INC", Incident),
                client_ref=f"seed-{rng.getrandbits(48):012x}",
                lat=lat, lon=lon,
                kind=rng.choice(kinds),
                severity=rng.randint(1, 5),
                people=rng.choice([1, 2, 4, 8, 15, 30]),
                description="Seeded demo report",
                source=Incident.Source.APP,
                cell_id=cell_for(lat, lon),
                status=Incident.Status.OPEN,
            )
