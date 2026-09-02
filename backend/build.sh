#!/usr/bin/env bash
# Render build step. Anything that must happen BEFORE the process starts.
#
# Kept in the repo rather than typed into the Render dashboard: a deploy you
# cannot read in git is a deploy nobody can fix at 2 a.m.
set -o errexit

pip install -r requirements.txt

# Collect admin + DRF assets for WhiteNoise to serve.
python manage.py collectstatic --no-input

# Schema first, always.
python manage.py migrate

# The road graph, from the committed compiled blob. NOT from Overpass: a deploy
# must not depend on a public API being up, and the raw OSM dump is 40 MB.
if [ -f data/roadgraph.bin ]; then
  python manage.py seed_roadgraph --from-blob data/roadgraph.bin
else
  echo "no data/roadgraph.bin -- routing will fall back to straight lines"
fi

# Demo data, only when explicitly asked for. SEED_DEMO is unset in a real
# deployment; a seed that runs on every deploy would wipe live incidents.
if [ "${SEED_DEMO:-}" = "true" ]; then
  python manage.py seed_demo --reset --scenario
fi
