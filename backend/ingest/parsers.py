"""S2 -- the parser. Turn a panicked 160-character message, or four keypresses,
into a structured incident. The real deliverable of the no-internet story.

BUILD THIS APP BACKWARDS. Write this file and its tests FIRST, on day 1, with no
models and no views. It is a pure string-in, dict-out module -- the tests run in
a second and need nothing else in the project to exist. That is what lets this
track work in parallel while Track 1 is still writing migrations.
"""

import os
import csv
import re
import hashlib
import requests
from datetime import datetime

# =============================================================================
# PHASE 1: STATIC DATA CACHING (Loaded once at import time)
# =============================================================================
PINCODE_CACHE = {}
csv_path = os.path.join(os.path.dirname(__file__), 'data', 'pincodes.csv')
try:
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            PINCODE_CACHE[row['pincode'].strip()] = (float(row['lat']), float(row['lon']))
except Exception:
    # Failsafe: If the file is missing during initial setup/testing, do not crash.
    pass

GEO_CACHE = {}

# Pre-compiled word lists for NLP fallback
HAZARD_WORDS = {
    'FLOOD': ['flood', 'water', 'baadh', 'बाढ़', 'ବନ୍ୟା', 'paani', 'ପାଣି'],
    'CYCLONE': ['cyclone', 'storm', 'toofan', 'तूफ़ान', 'ବାତ୍ୟା'],
    'LANDSLIDE': ['landslide', 'mudslide', 'bhuskhalan', 'ଭୂସ୍ଖଳନ']
}

# Flatten for O(1) keyword lookups
WORD_TO_KIND = {
    word.lower(): kind 
    for kind, words in HAZARD_WORDS.items() 
    for word in words
}

PEOPLE_WORDS = ['people', 'log', 'लोग', 'ଲୋକ', 'persons', 'families', 'ghar']

# =============================================================================
# PHASE 2: CORE PARSERS
# =============================================================================

def parse_sms(body, from_number):
    """Keyword grammar first, free text second. NEVER returns nothing."""
    
    # Deterministic ID for redelivery deduplication
    raw_string = f"{from_number}:{body}"
    client_ref = hashlib.sha256(raw_string.encode()).hexdigest()[:16]

    # Base draft for the worst-case scenario (Confidence 0.2)
    draft = {
        'client_ref': client_ref,
        'lat': 0.0,
        'lon': 0.0,
        'kind': "UNKNOWN",
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

    # Lazy import to prevent circular upward dependencies across apps
    try:
        from reports.services import infer_severity
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


# =============================================================================
# PHASE 3: TELEPHONY STATE MACHINE
# =============================================================================

def ivr_next(session, digit):
    """The keypad state machine."""
    # Handle session attributes gracefully based on existing state
    state = getattr(session, 'state', 'ASK_TYPE')
    answers = getattr(session, 'answers', {})
    
    done = False
    prompt = ""

    if state == 'ASK_TYPE':
        if digit == '1':
            answers['kind'] = 'FLOOD'
            state = 'ASK_PINCODE'
            prompt = "Enter your 6 digit pincode"
        elif digit == '2':
            answers['kind'] = 'CYCLONE'
            state = 'ASK_PINCODE'
            prompt = "Enter your 6 digit pincode"
        elif digit == '3':
            answers['kind'] = 'LANDSLIDE'
            state = 'ASK_PINCODE'
            prompt = "Enter your 6 digit pincode"
        else:
            prompt = "Press 1 flood, 2 cyclone, 3 landslide"
            
    elif state == 'ASK_PINCODE':
        current_pin = answers.get('pincode', '')
        if digit.isdigit():
            current_pin += digit
            answers['pincode'] = current_pin
        
        if len(current_pin) == 6 or digit == '#':
            state = 'ASK_COUNT'
            prompt = "How many people, then hash"
        else:
            prompt = "Enter your 6 digit pincode"
            
    elif state == 'ASK_COUNT':
        current_count = answers.get('people_raw', '')
        if digit.isdigit():
            current_count += digit
            answers['people_raw'] = current_count
            prompt = "How many people, then hash"
        elif digit == '#':
            answers['people'] = int(current_count) if current_count else 1
            state = 'DONE'
            prompt = "Help is on the way."
            done = True
        else:
            prompt = "How many people, then hash"
            
    elif state == 'DONE':
        prompt = "Help is on the way."
        done = True

    # Mutate the caller's session object
    session.state = state
    session.answers = answers
    
    # Save if it's a valid Django model instance
    if hasattr(session, 'save'):
        session.save()

    return prompt, done