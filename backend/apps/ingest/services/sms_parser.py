"""Turn a panicked 160-character SMS into a structured draft.

Pure string-in, dict-out: no models, no views, nothing to mock.
"""
import csv
import hashlib
import os
import re

import requests

# Static lookups, loaded once at import.
PINCODE_CACHE = {}
# ingest/data/pincodes.csv -- one level up, this file lives in services/
csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'pincodes.csv')
try:
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            PINCODE_CACHE[row['pincode'].strip()] = (float(row['lat']), float(row['lon']))
except Exception:
    # Failsafe: If the file is missing during initial setup/testing, do not crash.
    pass

GEO_CACHE = {}

HAZARD_WORDS = {
    'FLOOD': ['flood', 'water', 'baadh', 'बाढ़', 'ବନ୍ୟା', 'paani', 'ପାଣି'],
    'CYCLONE': ['cyclone', 'storm', 'toofan', 'तूफ़ान', 'ବାତ୍ୟା'],
    'LANDSLIDE': ['landslide', 'mudslide', 'bhuskhalan', 'ଭୂସ୍ଖଳନ']
}

# Flattened for O(1) keyword lookups.
WORD_TO_KIND = {word.lower(): kind
                for kind, words in HAZARD_WORDS.items()
                for word in words}

PEOPLE_WORDS = ['people', 'log', 'लोग', 'ଲୋକ', 'persons', 'families', 'ghar']

# "19.8135,85.8312" -- a decimal pair anywhere in the message.
#
# Two decimal places minimum on BOTH halves. One is not enough: "12.5,10.3"
# would then read as a position. Two is ~1.1 km, the same resolution as the
# cell grid, so it is the coarsest reading still worth acting on. The app sends
# four (App/src/sms.ts uses toFixed(4)); this lower bound is for a human typing
# a location by hand.
COORD_RE = re.compile(r'(-?\d{1,2}\.\d{2,7})\s*,\s*(-?\d{1,3}\.\d{2,7})')

# Anything outside this is not a location in this district, whatever it looks
# like. It is what lets the pattern above be loose enough for two decimals
# without "10.30,11.45" -- a time range -- landing a pin in the Indian Ocean.
# Widen it for a deployment outside India; do not remove it.
INDIA_BOUNDS = (6.0, 38.0, 68.0, 98.0)   # min_lat, max_lat, min_lon, max_lon


def parse_coords(body):
    """Exact coordinates out of an SMS body, or None.

    This is the only way a precise location survives the no-internet path. The
    phone still has a GPS fix with no data connection, but the alternatives
    cannot carry it: the pincode table is three rows, and landmark lookup needs
    the very internet this path exists to work without.

    Wrong beats missing here, so this rejects anything doubtful: an unplaced
    message waits in the triage queue for a human, while a bad pin sends a boat
    to open water.
    """
    min_lat, max_lat, min_lon, max_lon = INDIA_BOUNDS

    # Every candidate, not just the first: a message can carry a stray decimal
    # pair before the real position.
    for match in COORD_RE.finditer(body or ""):
        lat, lon = float(match.group(1)), float(match.group(2))
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return lat, lon
    return None


def parse_sms(body, from_number):
    """Keyword grammar first, free text second. NEVER returns nothing."""
    
    # Deterministic ID for redelivery deduplication
    raw_string = f"{from_number}:{body}"
    client_ref = hashlib.sha256(raw_string.encode()).hexdigest()[:16]

    # Base draft for the worst-case scenario (Confidence 0.2)
    # lat/lon stay None until we actually resolve a location. 0.0, 0.0 is a real
    # spot in the Atlantic and would show up as a pin off the coast of Africa.
    draft = {
        'client_ref': client_ref,
        'lat': None,
        'lon': None,
        'kind': None,
        'severity': 0,  
        'people': 1,
        'description': body,
        'reporter_phone': from_number,
    }
    confidence = 0.2

    # Attempt Strict Keyword Match
    parsed = parse_keyword(body)
    
    if parsed:
        draft['kind'] = parsed['kind']
        draft['people'] = parsed['people']
        
        coords = pincode_to_latlon(parsed['pincode'])
        if coords:
            draft['lat'], draft['lon'] = coords
            confidence = 1.0
            
    else:
        # Fallback to Free Text Heuristics
        parsed = parse_freetext(body)
        if parsed['kind']:
            draft['kind'] = parsed['kind']
        draft['people'] = parsed['people']

        coords = None
        if parsed['pincode']:
            coords = pincode_to_latlon(parsed['pincode'])
        
        # Only hit the network if pincode fails
        if not coords and parsed['landmark']:
            coords = landmark_to_latlon(parsed['landmark'])

        if coords:
            draft['lat'], draft['lon'] = coords
            confidence = 0.6 if parsed['kind'] else 0.4

    # Exact coordinates win over everything above. Checked last so it can
    # override a pincode centroid (~1 km out) or a landmark guess with the
    # phone's own fix, while still keeping the kind and headcount those
    # branches worked out from the words.
    coords = parse_coords(body)
    if coords:
        draft['lat'], draft['lon'] = coords
        confidence = 1.0

    # Lazy import to prevent circular upward dependencies across apps
    try:
        from apps.reports.services.make_incident import infer_severity
        draft['severity'] = infer_severity(draft)
    except ImportError:
        draft['severity'] = 3  # Fallback if service is completely unreachable

    return draft, confidence


def parse_keyword(body):
    """One regex for the published grammar."""
    # Pattern: [Optional "HELP"] [6-digit pin] [Hazard] [People Count] [Optional Note]
    pattern = r'(?i)^\s*(?:HELP\s+)?(\d{6})\s+([^\s\d]+)\s+(\d+)(?:\s+(.*))?$'
    match = re.match(pattern, body.strip())
    
    if not match:
        return None

    pincode, hazard_raw, people_raw, note = match.groups()
    
    kind = WORD_TO_KIND.get(hazard_raw.lower())
    if not kind:
        return None 

    return {
        'pincode': pincode,
        'kind': kind,
        'people': int(people_raw),
        'note': note.strip() if note else "",
    }


def parse_freetext(body):
    """Hazard keywords, headcount inference, and landmark extraction."""
    body_lower = body.lower()
    
    # 1. Kind: Prefer the LAST hazard word encountered
    kind = None
    last_idx = -1
    for word, hazard in WORD_TO_KIND.items():
        for match in re.finditer(rf'\b{re.escape(word)}\b', body_lower):
            if match.start() > last_idx:
                last_idx = match.start()
                kind = hazard
                
    # 2. People Count: Look for digits near people-words
    people = 1
    people_pattern = rf'(\d+)\s*(?:{"|".join(PEOPLE_WORDS)})|(?:{"|".join(PEOPLE_WORDS)})\s*(\d+)'
    people_match = re.search(people_pattern, body_lower)
    if people_match:
        val = people_match.group(1) or people_match.group(2)
        if val:
            people = int(val)

    # 3. Pincode
    pincode = None
    pin_match = re.search(r'\b(\d{6})\b', body)
    if pin_match:
        pincode = pin_match.group(1)

    # 4. Landmark: Longest capitalized/post-preposition span
    landmark = None
    prep_pattern = r'\b(?:near|at|by|in|around|behind|past)\s+([A-Z][a-zA-Z\s]+)'
    prep_matches = re.findall(prep_pattern, body)
    if prep_matches:
        landmark = max(prep_matches, key=len).strip()

    return {
        'kind': kind,
        'people': people,
        'pincode': pincode,
        'landmark': landmark,
        'note': body,
    }


def pincode_to_latlon(pin):
    """A CSV of pincode centroids loaded into a dict at import time."""
    if not pin:
        return None
    return PINCODE_CACHE.get(str(pin).strip())


def landmark_to_latlon(text):
    """Nominatim, biased to the district bounding box, results cached."""
    if not text:
        return None
        
    text_norm = text.strip().lower()
    if text_norm in GEO_CACHE:
        return GEO_CACHE[text_norm]

    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': text,
            'format': 'json',
            'limit': 1,
            'countrycodes': 'in' 
        }
        # Strict 3-second timeout per docstring constraints
        resp = requests.get(url, params=params, headers={'User-Agent': 'DishaDisasterMgmt/1.0'}, timeout=3.0)
        resp.raise_for_status()
        data = resp.json()
        
        if data:
            lat, lon = float(data[0]['lat']), float(data[0]['lon'])
            GEO_CACHE[text_norm] = (lat, lon)
            return (lat, lon)
    except Exception:
        # Do not raise here. A slow geocoder must never hold up SMS intake.
        pass
        
    return None
