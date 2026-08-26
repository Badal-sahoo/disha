"""S2 -- the parser. Turn a panicked 160-character message, or four keypresses,
into a structured incident. The real deliverable of the no-internet story.

BUILD THIS APP BACKWARDS. Write this file and its tests FIRST, on day 1, with no
models and no views. It is a pure string-in, dict-out module -- the tests run in
a second and need nothing else in the project to exist. That is what lets this
track work in parallel while Track 1 is still writing migrations.
"""


def parse_sms(body, from_number):
    """Keyword grammar first, free text second. NEVER returns nothing.

    IN:  body        = str    # the raw message, up to 160 chars
         from_number = str
    OUT: (draft, confidence)
         draft = {
           client_ref:     str,    # deterministic: hash(from_number + body + received_at)
                                   #   so a redelivered SMS dedupes on it
           lat:            float,
           lon:            float,
           kind:           str,    # "FLOOD" | "CYCLONE" | "LANDSLIDE"
           severity:       int,    # 1..5
           people:         int,
           description:    str,    # keep the ORIGINAL text here, always
           reporter_phone: str,
         }
         confidence = float 0..1
           1.0  clean keyword match with a valid pincode
           0.6  free text with a hazard word and a resolvable location
           0.2  nothing parsed -- location fell back to the sender's last known
                position, or the district centroid

    A message it cannot read STILL becomes a low-confidence incident for a human
    to triage. Never reject: an unparseable message is a person asking for help.

    USES: parse_keyword(body) -> dict | None      -- try this first
          parse_freetext(body) -> dict            -- fall through to this
          pincode_to_latlon(pin) -> (lat, lon) | None
          landmark_to_latlon(text) -> (lat, lon) | None
          reports.services.infer_severity(payload) -> int
                                                   -- only when no severity parsed

    CALLED BY: ingest/views.py SmsIntakeView.post
    """
    raise NotImplementedError("ingest.parsers.parse_sms -- Track 4 - Day 1")


def parse_keyword(body):
    """One regex for the published grammar.

    IN:  body = str          # "HELP 752001 FLOOD 12 stuck on roof"
    OUT: {
           pincode:  str,    # "752001"
           kind:     str,    # "FLOOD" | "CYCLONE" | "LANDSLIDE"
           people:   int,    # 12
           note:     str,    # "stuck on roof"
         } | None
         Returns None on no match SO THE CALLER CAN FALL THROUGH to free text.
         Do not raise here.

    Case-insensitive. Tolerate extra whitespace and a missing note. Accept the
    hazard word in any of the three languages the free-text parser knows, so a
    half-remembered format still lands on the fast path.
    """
    raise NotImplementedError("ingest.parsers.parse_keyword -- Track 4 - Day 1")


def parse_freetext(body):
    """Hazard keywords in English, Hindi and Odia; a digit near a people-word
    becomes the headcount. Crude, explainable, and good enough.

    IN:  body = str
    OUT: {
           kind:     str|None,   # "FLOOD" | "CYCLONE" | "LANDSLIDE" | None
           people:   int,        # default 1
           pincode:  str|None,   # any standalone 6-digit run
           landmark: str|None,   # the longest capitalised or post-preposition span
           note:     str,        # the original body, unmodified
         }

    Word lists to start from (extend on the day, they are cheap):
      FLOOD      flood, water, baadh, बाढ़, ବନ୍ୟା, paani, ପାଣି
      CYCLONE    cyclone, storm, toofan, तूफ़ान, ବାତ୍ୟା
      LANDSLIDE  landslide, mudslide, bhuskhalan, ଭୂସ୍ଖଳନ
    people-words: people, log, लोग, ଲୋକ, persons, families, ghar

    Prefer the LAST hazard word in the message -- people correct themselves
    mid-sentence more often than they change subject.
    """
    raise NotImplementedError("ingest.parsers.parse_freetext -- Track 4 - Day 1")


def pincode_to_latlon(pin):
    """A CSV of pincode centroids loaded into a dict at import time.

    IN:  pin = str            # "752001"
    OUT: (lat, lon) | None

    DATA: ingest/data/pincodes.csv, columns pincode,lat,lon. Load it ONCE into a
          module-level dict at import -- no network, no rate limit,
          sub-millisecond, and it works with the internet unplugged, which is
          the entire point of this path.

    ACCURACY: ~1-3 km. That is exactly what corroboration clustering exists to
    fix -- five vague reports from one pincode still converge on one cell.
    """
    raise NotImplementedError("ingest.parsers.pincode_to_latlon -- Track 4 - Day 1")


def landmark_to_latlon(text):
    """Nominatim, biased to the district bounding box, results cached.

    IN:  text = str           # "near Konark temple"
    OUT: (lat, lon) | None

    ONLY reached when there is no pincode -- it is a network call with a rate
    limit, and this whole app exists for the case where there is no network.

    CACHE every lookup (a dict, or a small table) keyed on the normalised text.
    Set a 3-second timeout and return None on any failure; a slow geocoder must
    never hold up an SMS intake.
    """
    raise NotImplementedError("ingest.parsers.landmark_to_latlon -- Track 4 - Day 2")


def ivr_next(session, digit):
    """The keypad state machine. One function serves both the browser simulator
    and a real telephony webhook.

    IN:  session = ingest.models.IvrSession   # state is a plain string
         digit   = str                        # "0".."9", "*", "#", or ""
    OUT: (prompt, done)
           prompt = str    what to say next
           done   = bool   True once enough is collected to create an incident

    STATES and what each stores into session.answers:
      ASK_TYPE     "Press 1 flood, 2 cyclone, 3 landslide"   -> answers["kind"]
      ASK_PINCODE  "Enter your 6 digit pincode"              -> answers["pincode"]
                   (accumulate digits; advance on the 6th or on #)
      ASK_COUNT    "How many people, then hash"              -> answers["people"]
      DONE         "Help is on the way. Your code is ..."    -> done=True

    Mutate session.state and session.answers, then session.save(). The CALLER
    creates the incident when done is True -- keep this function transport-
    agnostic and side-effect-free beyond its own row.

    INVALID DIGIT: re-prompt, do not advance and do not error. A frightened
    person pressing the wrong key must not lose the call.
    """
    raise NotImplementedError("ingest.parsers.ivr_next -- Track 4 - Day 2")
