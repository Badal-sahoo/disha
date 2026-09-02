"""Download the district's roads from OpenStreetMap and store the graph in Postgres.

Run this once before the demo. Overpass is slow and rate-limits hard, so the raw
download is cached on disk and a rebuild costs nothing.

    python manage.py seed_roadgraph
    python manage.py seed_roadgraph --cache
    python manage.py seed_roadgraph --bbox 19.6 85.5 20.2 86.3 --grid 3

Then set USE_ROAD_GRAPH=True in backend/.env and restart daphne.
"""
import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.dispatch.models import RoadGraph
from apps.dispatch.roadnet import build_network, fetch_osm_roads, merge_osm, tiles


class Command(BaseCommand):
    help = "Fetch OSM roads for the district and store the routing graph in the database."

    def add_arguments(self, parser):
        parser.add_argument("--name", default="puri", help="What to call this graph.")
        parser.add_argument("--bbox", nargs=4, type=float,
                            metavar=("MIN_LAT", "MIN_LON", "MAX_LAT", "MAX_LON"))
        parser.add_argument("--grid", type=int, default=3,
                            help="Split the box into grid x grid downloads.")
        parser.add_argument("--cache", action="store_true",
                            help="Reuse the last download instead of asking Overpass again.")
        parser.add_argument("--export", metavar="PATH",
                            help="Write the COMPILED graph already in the database to a "
                                 "file, so it can be shipped without the 40 MB OSM dump.")
        parser.add_argument("--from-blob", metavar="PATH",
                            help="Load a compiled graph written by --export. This is the "
                                 "production path: Overpass is slow, rate-limits, and is "
                                 "not something a deploy should depend on.")

    def handle(self, *args, **options):
        bbox = options["bbox"] or settings.ROAD_GRAPH_BBOX
        name = options["name"]

        if options["export"]:
            return self._export(name, Path(options["export"]))
        if options["from_blob"]:
            return self._import(name, Path(options["from_blob"]), bbox)

        min_lat, min_lon, max_lat, max_lon = bbox
        raw_path = Path(settings.BASE_DIR) / "data" / f"{name}.osm.json"

        if options["cache"]:
            if not raw_path.exists():
                raise CommandError(f"no cached download at {raw_path} -- run without --cache")
            self.stdout.write(f"reusing {raw_path}")
            osm = json.loads(raw_path.read_text())
        else:
            osm = self._download(bbox, options["grid"], raw_path)

        self.stdout.write(f"{len(osm['elements'])} OSM elements")

        network = build_network(osm)
        blob = network.to_bytes()

        RoadGraph.objects.update_or_create(
            name=name,
            defaults={
                "min_lat": min_lat, "min_lon": min_lon,
                "max_lat": max_lat, "max_lon": max_lon,
                "node_count": network.node_count,
                "edge_count": network.edge_count,
                "data": blob,
            },
        )

        self.stdout.write(self.style.SUCCESS(
            f"stored '{name}': {network.node_count} nodes, {network.edge_count} edges, "
            f"{len(blob) // 1024} KB"))
        self.stdout.write("set USE_ROAD_GRAPH=True in backend/.env and restart daphne")

    def _say(self, message, style=None):
        """Write a progress line AND flush it.

        Django buffers self.stdout when it is not a terminal, so a run started
        with `nohup ... &` produced an empty log file for ninety minutes while
        it was working perfectly. A long download you cannot watch is one you
        cannot tell from a hung one.
        """
        self.stdout.write(style(message) if style else message)
        self.stdout.flush()

    def _download(self, bbox, grid, raw_path):
        """Fetch the box a tile at a time, because Overpass refuses it whole.

        AND SUB-SPLIT ANYTHING THAT TIMES OUT.

        One failed tile used to kill the whole run: every mirror is tried, they
        all 504, and forty minutes of successful tiles are thrown away. That is
        what happened three times in a row after `track` and `path` were added
        to the road filter -- roughly double the ways per tile, and the public
        Overpass instances stop answering.

        A 504 means "this query was too big for me", not "this query is wrong".
        So a tile that fails is cut into four and each quarter is asked for
        separately, down to a floor. Slower, and it finishes.
        """
        boxes = list(tiles(*bbox, grid=grid))
        self._say(f"downloading {len(boxes)} tiles (Overpass is slow and rate-limits)")

        chunks = []
        for n, tile in enumerate(boxes, start=1):
            self._say(f"  tile {n}/{len(boxes)} {tile[0]:.2f},{tile[1]:.2f}")
            chunks.extend(self._fetch_tile(tile))

        osm = merge_osm(chunks)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(osm))
        self.stdout.write(f"  cached at {raw_path}")
        return osm

    # Stop splitting below this. A tile this small that still times out is a
    # network problem, not a size problem, and splitting further will not help.
    MIN_TILE_DEGREES = 0.02

    # Ask the same tile this many times before deciding it is too big. Overpass
    # refuses plenty of requests it would happily answer thirty seconds later,
    # and splitting on the first refusal quadruples the request count for what
    # was only ever a busy minute.
    TILE_ATTEMPTS = 3

    def _fetch_tile(self, tile, depth=0):
        """One tile, or its quarters if Overpass keeps refusing it."""
        min_lat, min_lon, max_lat, max_lon = tile
        pad = "  " * depth

        for attempt in range(1, self.TILE_ATTEMPTS + 1):
            try:
                return [fetch_osm_roads(
                    *tile, on_status=lambda msg: self._say(f"    {pad}{msg}"))]
            except RuntimeError:
                if attempt < self.TILE_ATTEMPTS:
                    wait = 10 * attempt
                    self._say(f"    {pad}refused ({attempt}/{self.TILE_ATTEMPTS}) "
                              f"-- waiting {wait}s", self.style.WARNING)
                    time.sleep(wait)

        if (max_lat - min_lat) <= self.MIN_TILE_DEGREES:
            raise CommandError(
                f"tile {min_lat:.3f},{min_lon:.3f} is already "
                f"{max_lat - min_lat:.3f} deg and is still being refused. That is a "
                f"network problem, not a size one -- Overpass is overloaded. Wait and "
                f"run it again; the cached download is untouched.")

        mid_lat = (min_lat + max_lat) / 2
        mid_lon = (min_lon + max_lon) / 2
        self._say(f"    {pad}still refused -- splitting into 4", self.style.WARNING)
        time.sleep(5)

        quarters = [
            (min_lat, min_lon, mid_lat, mid_lon),
            (min_lat, mid_lon, mid_lat, max_lon),
            (mid_lat, min_lon, max_lat, mid_lon),
            (mid_lat, mid_lon, max_lat, max_lon),
        ]
        out = []
        for quarter in quarters:
            out.extend(self._fetch_tile(quarter, depth + 1))
        return out

    def _export(self, name, path):
        """Dump the compiled graph out of the database.

        The raw OSM download is ~40 MB and has no business in a git repository.
        The COMPILED graph is a few MB and is the only thing production needs, so
        that is what gets shipped.
        """
        row = RoadGraph.objects.filter(name=name).first()
        if row is None:
            raise CommandError(f"no RoadGraph named '{name}' in this database")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(row.data))
        self.stdout.write(self.style.SUCCESS(
            f"exported '{name}' ({row.node_count} nodes, {row.edge_count} edges) "
            f"-> {path} ({path.stat().st_size // 1024} KB)"))

    def _import(self, name, path, bbox):
        """Load a compiled graph into this database. No network, no Overpass."""
        if not path.exists():
            raise CommandError(f"no compiled graph at {path} -- run --export first")

        from apps.dispatch.roadnet import RoadNetwork

        blob = path.read_bytes()
        network = RoadNetwork.from_bytes(blob)
        min_lat, min_lon, max_lat, max_lon = bbox

        RoadGraph.objects.update_or_create(
            name=name,
            defaults={
                "min_lat": min_lat, "min_lon": min_lon,
                "max_lat": max_lat, "max_lon": max_lon,
                "node_count": network.node_count,
                "edge_count": network.edge_count,
                "data": blob,
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f"loaded '{name}': {network.node_count} nodes, {network.edge_count} edges"))
