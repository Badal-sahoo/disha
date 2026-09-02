/**
 * Mirrors backend/realtime/events.py. Change one, change both -- these strings
 * are the contract between the socket and the reducer.
 */
export const WS_EVENTS = {
  INCIDENT_NEW: "incident.new",
  INCIDENT_UPDATE: "incident.update",
  RESOURCE_UPDATE: "resource.update",
  ASSIGNMENT_NEW: "assignment.new",
  ASSIGNMENT_UPDATE: "assignment.update",
  SHELTER_UPDATE: "shelter.update",
  ZONE_NEW: "zone.new",
  ZONE_REMOVED: "zone.removed",
  ALERT_NEW: "alert.new",
  KPI_UPDATE: "kpi.update",
};

/** Which store collection each event patches. Drives applyDelta's dispatch. */
export const EVENT_TO_COLLECTION = {
  "incident.new": "incidents",
  "incident.update": "incidents",
  "resource.update": "resources",
  "assignment.new": "assignments",
  "assignment.update": "assignments",
  "shelter.update": "shelters",
  "zone.new": "zones",
  "zone.removed": "zones",
  "alert.new": "alerts",
};

export const INCIDENT_KINDS = ["FLOOD", "CYCLONE", "LANDSLIDE"];
export const INCIDENT_STATUSES = ["OPEN", "ASSIGNED", "RESOLVED"];

export const RESOURCE_KINDS = ["TEAM", "BOAT", "TRUCK", "AMBULANCE"];

/**
 * The glyph that stands for each unit kind on the map and in the roster.
 *
 * These are drawn onto a canvas and registered with map.addImage(), NOT set as
 * a symbol text-field: the basemap is raster and carries no glyph stack, so a
 * text-field renders nothing at all.
 *
 * ponytail: TEAM is a ZWJ sequence; a browser without it falls back to the two
 * component glyphs rather than tofu. Swap for a single codepoint if that shows.
 */
export const KIND_EMOJI = {
  TEAM: "🧑‍🚒",
  BOAT: "🚤",
  TRUCK: "🚚",
  AMBULANCE: "🚑",
};

/** Every shelter is a house, whatever its status -- colour carries the status. */
export const SHELTER_EMOJI = "🏠";

/**
 * A hospital gets its own glyph.
 *
 * The backend now distinguishes Shelter.kind SHELTER from HOSPITAL, because an
 * ambulance carrying a casualty has to be routed somewhere with a doctor in it.
 * Drawing both as the same house on the map would hide the one decision that
 * distinction exists to make.
 */
export const HOSPITAL_EMOJI = "🏥";

export const RESOURCE_STATUSES = [
  "IDLE",
  "ENROUTE",
  "ONSCENE",
  "TRANSPORTING",
  "OUT_OF_SERVICE",
];

export const SHELTER_STATUSES = ["OPEN", "FULL", "INACCESSIBLE"];

/** ACCEPTED -> EN_ROUTE -> ON_SCENE -> TRANSPORTING -> COMPLETE */
export const ASSIGNMENT_STATUSES = [
  "PROPOSED",
  "DISPATCHED",
  "ACCEPTED",
  "EN_ROUTE",
  "ON_SCENE",
  "TRANSPORTING",
  "COMPLETE",
];

/**
 * TWO COLOUR AXES, AND THEY MUST NOT MEET.
 *
 * An operator reads two different questions off the same map at the same time:
 *   HOW BAD is it   -> severity, CAP severity      -> WARM ramp (yellow -> red)
 *   WHAT STATE is it -> unit status, shelter status -> COOL + neutral
 *
 * They used to overlap: ONSCENE was #f08c00, sitting in the middle of the
 * severity ramp, and severity 5 was byte-identical to the interface's --danger.
 * A busy map was unreadable because "urgent" and "a truck is parked there" were
 * the same orange. Keep warm for hazard and cool for state, and the two stay
 * separable at a glance without a legend.
 *
 * The interface chrome itself carries NO hue -- see styles.css. Every saturated
 * colour on screen is data.
 */

/** Unit status. Cool ramp: the further along the job, the further round the wheel. */
export const STATUS_COLORS = {
  IDLE: "#2fa98a",           // teal -- available
  ENROUTE: "#3e8fd0",        // blue -- travelling
  ONSCENE: "#6e5ac8",        // indigo -- working
  TRANSPORTING: "#b45fa8",   // magenta -- carrying people out
  OUT_OF_SERVICE: "#5c7183", // slate -- not in the solve
};

/** Severity 1..5 -> colour. Used by pins, heat ramp and zone fills. Warm only. */
export const SEVERITY_COLORS = {
  1: "#f2c14e",
  2: "#eda23b",
  3: "#e2762f",
  4: "#d14c28",
  5: "#b02020",
};

/** IMD ladder for CAP alert severity. Same warm family as SEVERITY_COLORS on
    purpose: both answer "how bad", so they read as one language. */
export const CAP_SEVERITY_COLORS = {
  Minor: "#f2c14e",
  Moderate: "#eda23b",
  Severe: "#d14c28",
  Extreme: "#8e1a1a",
};

/**
 * Shelter status. Cool/neutral, because "how full" is a state and not a hazard.
 * These used to be three hexes typed inline in geojson.js -- the map and this
 * file then disagreed about what "FULL" looked like.
 */
export const SHELTER_COLORS = {
  OPEN: "#2fa98a",
  FULL: "#5c7183",
  INACCESSIBLE: "#8e1a1a",
};

/* The basemap itself lives in shared/utils/basemap.js, configured through
   VITE_MAP_TILE_URL -- there is no style URL to set here. */
export const MAP_DEFAULTS = {
  center: [
    Number(import.meta.env.VITE_MAP_CENTER_LON ?? 85.8312),
    Number(import.meta.env.VITE_MAP_CENTER_LAT ?? 19.8135),
  ], // MapLibre wants [lon, lat] -- this is the GeoJSON boundary
  zoom: Number(import.meta.env.VITE_MAP_ZOOM ?? 11),
};

/** MapLibre source ids, pre-registered at init so no layer is ever re-added. */
export const SOURCES = {
  INCIDENTS: "incidents",
  RISK: "risk",
  SEA: "sea",
  SCENES: "scenes",
  HEAT: "heat",
  RESOURCES: "resources",
  SHELTERS: "shelters",
  ZONES: "zones",
  ASSIGNMENTS: "assignments",
  ALERTS: "alerts",
};

/** The dispatch horizon from backend settings. cost = w * (eta - 120). */
export const HORIZON_MIN = 120;
