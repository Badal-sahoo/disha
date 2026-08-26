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

/** The three dispatch policies. The A/B toggle flips between them. */
export const POLICIES = ["OPTIMIZED", "GREEDY", "GREEDY_SEVERITY"];

export const POLICY_LABELS = {
  OPTIMIZED: "Optimised",
  GREEDY: "Nearest available",
  GREEDY_SEVERITY: "Nearest, severity first",
};

export const INCIDENT_KINDS = ["FLOOD", "CYCLONE", "LANDSLIDE"];
export const INCIDENT_STATUSES = ["OPEN", "ASSIGNED", "RESOLVED"];

export const RESOURCE_KINDS = ["TEAM", "BOAT", "TRUCK", "AMBULANCE"];
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

/** Colour by unit status. State readable at a glance, no legend lookup. */
export const STATUS_COLORS = {
  IDLE: "#2f9e44",
  ENROUTE: "#1c7ed6",
  ONSCENE: "#f08c00",
  TRANSPORTING: "#7048e8",
  OUT_OF_SERVICE: "#868e96",
};

/** Severity 1..5 -> colour. Used by pins, heat ramp and zone fills. */
export const SEVERITY_COLORS = {
  1: "#94d82d",
  2: "#fcc419",
  3: "#ff922b",
  4: "#f76707",
  5: "#e03131",
};

/** IMD ladder for CAP alert severity. */
export const CAP_SEVERITY_COLORS = {
  Minor: "#2f9e44",
  Moderate: "#fcc419",
  Severe: "#f76707",
  Extreme: "#c92a2a",
};

export const MAP_DEFAULTS = {
  style: import.meta.env.VITE_MAP_STYLE ?? "https://demotiles.maplibre.org/style.json",
  center: [
    Number(import.meta.env.VITE_MAP_CENTER_LON ?? 85.8312),
    Number(import.meta.env.VITE_MAP_CENTER_LAT ?? 19.8135),
  ], // MapLibre wants [lon, lat] -- this is the GeoJSON boundary
  zoom: Number(import.meta.env.VITE_MAP_ZOOM ?? 10),
};

/** MapLibre source ids, pre-registered at init so no layer is ever re-added. */
export const SOURCES = {
  INCIDENTS: "incidents",
  HEAT: "heat",
  RESOURCES: "resources",
  SHELTERS: "shelters",
  ZONES: "zones",
  ASSIGNMENTS: "assignments",
  ALERTS: "alerts",
  SUPPLY: "supply",
};

/** The dispatch horizon from backend settings. cost = w * (eta - 120). */
export const HORIZON_MIN = 120;
