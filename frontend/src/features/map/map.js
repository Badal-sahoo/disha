/**
 * creates the map, and keeps the live store in step with the socket.
 *
 * COORDINATE ORDER: MapLibre and GeoJSON want [lon, lat]; everything else in
 * this project is (lat, lon). shared/utils/geojson.js does every flip.
 *
 * Each feature paints its OWN layer through its own hook (useZones, useAlerts,
 * useFleetLayer, ...). This file only paints the two sources nobody else owns:
 * incidents and shelters.
 */
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { useLiveStore } from "@/shared/store/liveStore";
import { buildBasemapStyle } from "@/shared/utils/basemap";
import {
  EVENT_TO_COLLECTION,
  MAP_DEFAULTS,
  SEVERITY_COLORS,
  SOURCES,
} from "@/shared/utils/constants";
import {
  collection,
  toIncidentGeoJSON,
  toSceneGeoJSON,
  toShelterGeoJSON,
} from "@/shared/utils/geojson";

import { RISK_RAMP, toRiskGeoJSON, toSeaMaskGeoJSON } from "./risk";

import { fetchState } from "./api";

const EMPTY = collection([]);

/**
 * How the basemap tiles are treated per theme.
 *
 * The dashboard chrome is deep navy and the basemap is a bright raster, which
 * put a hard luminance cliff in the middle of the default screen. Rather than
 * swap the tile provider -- operators need the map they recognise, with the road
 * colours and place names they already know -- the RASTER LAYER ALONE is knocked
 * back. Our own overlays are vector layers and keep their full saturation, so
 * severity and status stay exactly as loud as they were while the ground behind
 * them settles down.
 */
const BASEMAP_PAINT = {
  dark: {
    "raster-saturation": -0.55,
    "raster-brightness-min": 0.04,
    "raster-brightness-max": 0.62,
    "raster-contrast": 0.12,
    "raster-opacity": 0.82,
  },
  light: {
    "raster-saturation": -0.28,
    "raster-brightness-min": 0.06,
    "raster-brightness-max": 1,
    "raster-contrast": -0.04,
    "raster-opacity": 0.95,
  },
};

/** IN: map, theme = "dark" | "light". Safe to call before the style loads. */
export function applyBasemapTheme(map, theme) {
  if (!map || !map.getLayer?.("basemap")) return;
  const paint = BASEMAP_PAINT[theme] ?? BASEMAP_PAINT.dark;
  for (const [prop, value] of Object.entries(paint)) {
    map.setPaintProperty("basemap", prop, value);
  }
  map.setPaintProperty("background", "background-color", theme === "dark" ? "#0b1620" : "#e6e2dc");

  // The sea mask has to sit in the tiles' own water tone, or it reads as a
  // grey slab bolted over the bay.
  if (map.getLayer("risk-sea-mask")) {
    map.setPaintProperty("risk-sea-mask", "fill-color",
      theme === "dark" ? "rgba(24, 52, 68, 0.66)" : "rgba(170, 205, 222, 0.72)");
  }
}

/* A pin needs a dark casing, not a white one. White worked on pale tiles and
   disappeared over sand, rooftops and the dimmed dark-theme basemap alike. */
const CASING = "rgba(11, 22, 32, 0.85)";

/**
 * Radius that grows with zoom, so a marker keeps its proportion to the streets
 * underneath it.
 *
 * THIS IS WHY THE EMOJI ARE GONE. They were symbol layers at a fixed
 * icon-size, so zooming in left a 🚤 the same number of screen pixels while the
 * road it sat on got wider -- the pin shrank against the map and the glyph
 * turned to mush. They also rendered as a different picture on every operating
 * system. Circles are drawn by the GPU at whatever size we ask for, at any
 * zoom, identically everywhere.
 *
 * SHAPE now carries WHAT a thing is, colour still carries its state:
 *   filled disc  = an incident        (warm, severity)
 *   hollow ring  = a rescue unit      (cool, status)
 *   ringed disc  = a shelter/hospital (cool, room left)
 */
const zoomRadius = (near, far) => [
  "interpolate", ["linear"], ["zoom"], 9, near, 16, far,
];

/**
 * Every layer, in paint order: fills at the bottom, then lines, then the pins
 * on top. MapLibre draws them in the order they are added.
 *
 * ["get", "color"] means "read the colour from the feature's properties", so
 * the colour is decided where the GeoJSON is built, not here.
 */
/**
 * Above this zoom the map shows EVERY FAMILY; below it, one circle per scene.
 *
 * Zoom 13 is roughly a 1 km view. Further out, thirty family pins in one
 * village are a blob nobody can count -- one circle carrying "30 families" is
 * the honest summary. Closer in, the blob is the point: a boat crew routes
 * house to house, and the individual positions are the work.
 */
const FAMILY_ZOOM = 13;

const LAYERS = [
  // Flood risk, at the very bottom so everything else sits on top of it.
  //
  // A heatmap over samples of the shoreline, NOT three filled bands. Density is
  // highest at the water and decays inland, so the ramp in risk.js turns
  // distance-from-shore into a continuous red -> orange -> yellow -> green wash
  // with no edges anywhere. See risk.js for why that matters.
  { id: "risk-heat", source: SOURCES.RISK, type: "heatmap",
    paint: {
      "heatmap-weight": 1,
      // The radius is what sets how far inland the wash reaches. It is in SCREEN
      // pixels, so it has to grow with zoom or the band would shrink to a thin
      // line on the coast as you zoom in. These values hold it at roughly 25 km
      // of ground from zoom 8 to zoom 14.
      "heatmap-radius": ["interpolate", ["exponential", 2], ["zoom"],
                         8, 55, 11, 300, 14, 900],
      // Samples are 1 km apart and overlap heavily, so without this the middle
      // of the run saturates and the whole coast reads as flat red.
      "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 8, 0.5, 14, 0.25],
      "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], ...RISK_RAMP],
      // Kept well under half. At 0.85 the wash buried the road network, and a
      // risk layer that hides the roads you dispatch along is worth less than
      // no risk layer.
      "heatmap-opacity": 0.5,
    } },

  // Clips the wash off the water; see toSeaMaskGeoJSON. Colour is set per theme
  // by applyBasemapTheme, because it has to match whatever the tiles paint.
  { id: "risk-sea-mask", source: SOURCES.SEA, type: "fill",
    paint: { "fill-color": "rgba(30, 58, 74, 0.62)" } },

  // Cut roads and flooded areas.
  { id: "zones-fill", source: SOURCES.ZONES, type: "fill",
    paint: { "fill-color": ["get", "color"], "fill-opacity": 0.16 } },
  { id: "zones-line", source: SOURCES.ZONES, type: "line",
    layout: { "line-join": "round" },
    paint: { "line-color": ["get", "color"], "line-width": 1.5, "line-opacity": 0.9 } },

  // Dispatch routes, drawn as a road is drawn: a dark casing underneath so the
  // line reads over any tile, then the coloured line on top. One flat 2px dash
  // over a photographic basemap was close to invisible on the tiles that matter.
  { id: "assignments-casing", source: SOURCES.ASSIGNMENTS, type: "line",
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": "rgba(11, 22, 32, 0.55)",
             "line-width": ["interpolate", ["linear"], ["zoom"], 9, 4, 16, 8] } },
  { id: "assignments-line", source: SOURCES.ASSIGNMENTS, type: "line",
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": "#3e8fd0",
             "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1.8, 16, 4],
             "line-dasharray": [0, 4, 3] } },

  // Pins last, so they sit on top of every fill.
  //
  // Each shelter and unit is a coloured dot marking the exact spot, with its
  // glyph standing just above it. The dot keeps carrying the STATUS colour --
  // a glyph alone cannot say whether a boat is idle or already en route.

  // A soft bloom under the worst incidents only. Severity is the one thing an
  // operator has to find without looking for it, and radius alone stops
  // separating 4 from 5 as soon as two pins overlap.
  { id: "incidents-halo", source: SOURCES.INCIDENTS, type: "circle",
    minzoom: FAMILY_ZOOM,
    filter: [">=", ["get", "severity"], 3],
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["get", "severity"], 3, 14, 5, 26],
      "circle-color": ["get", "color"],
      "circle-opacity": 0.2,
      "circle-blur": 0.7,
    } },

  // A severity-5 report with nobody sent to it is the one thing on this screen
  // that must never be missed, so it is the one thing that moves. The ring is
  // driven from the same frame loop as the route dashes; see animateRoutes.
  { id: "incidents-critical", source: SOURCES.INCIDENTS, type: "circle",
    minzoom: FAMILY_ZOOM,
    filter: ["all", ["==", ["get", "severity"], 5], ["==", ["get", "status"], "OPEN"]],
    paint: {
      "circle-radius": 14,
      "circle-color": "rgba(0,0,0,0)",
      "circle-stroke-width": 1.5,
      "circle-stroke-color": SEVERITY_COLORS[5],
      "circle-stroke-opacity": 0.8,
    } },

  // A place people are taken TO: a solid disc inside a pale ring, so it reads
  // as a building rather than as another thing that moves.
  { id: "shelters-point", source: SOURCES.SHELTERS, type: "circle",
    paint: {
      "circle-radius": zoomRadius(4, 9),
      "circle-color": ["get", "color"],
      "circle-stroke-width": zoomRadius(2, 4),
      "circle-stroke-color": "rgba(232, 237, 240, 0.75)",
    } },

  // A unit is a HOLLOW ring: transparent in the middle, so an incident pin
  // underneath still shows through when a boat is standing on top of it.
  { id: "resources-point", source: SOURCES.RESOURCES, type: "circle",
    paint: {
      "circle-radius": zoomRadius(5, 11),
      "circle-color": "rgba(0, 0, 0, 0)",
      "circle-stroke-width": zoomRadius(2.5, 5),
      "circle-stroke-color": ["get", "color"],
    } },
  // A dark hairline outside the ring, so a pale unit still reads on pale tiles.
  { id: "resources-casing", source: SOURCES.RESOURCES, type: "circle",
    paint: {
      "circle-radius": zoomRadius(6.5, 14),
      "circle-color": "rgba(0, 0, 0, 0)",
      "circle-stroke-width": 1,
      "circle-stroke-color": CASING,
    } },
  // ZOOMED IN: one small translucent disc per family. Deliberately soft, so
  // thirty of them overlapping still read as thirty rather than one dark mass.
  { id: "incidents-point", source: SOURCES.INCIDENTS, type: "circle",
    minzoom: FAMILY_ZOOM,
    paint: {
      // Bigger than a unit dot on purpose. A report outranks the truck going to
      // it, and the old range topped out smaller than the vehicle glyphs.
      "circle-radius": [
        "interpolate", ["linear"], ["zoom"],
        9, ["interpolate", ["linear"], ["get", "severity"], 1, 4, 5, 10],
        16, ["interpolate", ["linear"], ["get", "severity"], 1, 9, 5, 22],
      ],
      "circle-color": ["get", "color"],
      // A report with a unit on the way has been dealt with. Keeping it as loud
      // as an unanswered one is how an operator loses the ones still waiting.
      "circle-opacity": ["case", ["==", ["get", "status"], "OPEN"], 1, 0.45],
      "circle-stroke-width": 1.2,
      "circle-stroke-color": CASING,
      "circle-opacity": ["case", ["==", ["get", "status"], "OPEN"], 0.62, 0.3],
    } },

  // ZOOMED OUT: the whole village as ONE circle, sized by how many families
  // are in it. This is the same grouping the dispatch cards use, so what the
  // operator counts on the map is what they get on the card.
  { id: "incidents-scene-halo", source: SOURCES.SCENES, type: "circle",
    maxzoom: FAMILY_ZOOM,
    filter: [">=", ["get", "severity"], 4],
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["get", "families"], 1, 16, 30, 40],
      "circle-color": ["get", "color"],
      "circle-opacity": 0.16,
      "circle-blur": 0.7,
    } },
  { id: "incidents-scene", source: SOURCES.SCENES, type: "circle",
    maxzoom: FAMILY_ZOOM,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["get", "families"], 1, 7, 30, 22],
      "circle-color": ["get", "color"],
      "circle-opacity": ["case", ["==", ["get", "status"], "OPEN"], 0.55, 0.28],
      "circle-stroke-width": 1.5,
      "circle-stroke-color": CASING,
    } },
  // NO TEXT LABEL HERE. A symbol layer with a text-field renders NOTHING on
  // this map: the basemap is raster and carries no glyph stack, which is the
  // same trap the old emoji pins worked around by drawing to a canvas. The
  // circle is sized by family count instead, and the exact number is one click
  // away in the popup.
];

/* Which layers answer a click, and how each one describes itself. */
const POPUP_LAYERS = ["incidents-point", "incidents-scene", "resources-point",
                      "shelters-point"];

const esc = (v) =>
  String(v ?? "--").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]
  );

const row = (label, value) => `<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`;

/**
 * The card shown when a pin is clicked.
 *
 * Before this there was no way to identify anything on the map at all: you could
 * see a dot and not learn which unit it was, how full a shelter was, or what a
 * report actually said. Everything here is already on the feature -- no fetch.
 */
function popupHTML(feature) {
  const p = feature.properties ?? {};
  const swatch = `<span class="dot" style="background:${esc(p.color)}"></span>`;

  if (feature.layer.id === "incidents-scene") {
    return `<div class="map-pop">
      <div class="map-pop__head">${swatch}<span class="map-pop__code">${esc(p.code)}</span></div>
      <dl class="map-pop__rows">
        ${row("Families", p.families)}
        ${row("People", p.people)}
        ${row("Severity", p.severity)}
        ${row("Kind", String(p.kind ?? "").toLowerCase())}
      </dl>
      <p class="map-pop__hint">Zoom in to see each family</p></div>`;
  }

  if (feature.layer.id === "incidents-point") {
    return `<div class="map-pop">
      <div class="map-pop__head">${swatch}<span class="map-pop__code">${esc(p.code)}</span></div>
      <dl class="map-pop__rows">
        ${row("Kind", String(p.kind ?? "").toLowerCase())}
        ${row("Severity", p.severity)}
        ${row("People", p.people)}
        ${row("Status", String(p.status ?? "").toLowerCase())}
      </dl></div>`;
  }

  if (feature.layer.id === "resources-point") {
    return `<div class="map-pop">
      <div class="map-pop__head">${swatch}<span class="map-pop__code">${esc(p.code)}</span></div>
      <dl class="map-pop__rows">
        ${row("Kind", String(p.kind ?? "").toLowerCase())}
        ${row("Status", String(p.status ?? "").toLowerCase().replace("_", " "))}
        ${row("Capacity", p.capacity)}
      </dl></div>`;
  }

  const isHospital = p.kind === "HOSPITAL";
  return `<div class="map-pop">
    <div class="map-pop__head">${swatch}<span class="map-pop__code">${esc(p.name || p.code)}</span></div>
    <dl class="map-pop__rows">
      ${row("Type", isHospital ? "hospital" : "cyclone shelter")}
      ${row(isHospital ? "Beds used" : "Occupancy", `${p.occupancy ?? "--"} / ${p.capacity ?? "--"}`)}
      ${row(isHospital ? "Beds free" : "Room left", p.remaining)}
      ${row("Status", String(p.status ?? "").toLowerCase())}
    </dl></div>`;
}

/** Click to identify, and a pointer cursor so the pins look clickable. */
function addPopups(map) {
  const popup = new maplibregl.Popup({
    closeButton: true,
    closeOnClick: true,
    offset: 14,
    maxWidth: "280px",
  });

  for (const id of POPUP_LAYERS) {
    if (!map.getLayer(id)) continue;
    map.on("click", id, (e) => {
      const feature = e.features?.[0];
      if (!feature) return;
      popup.setLngLat(feature.geometry.coordinates.slice()).setHTML(popupHTML(feature)).addTo(map);
    });
    map.on("mouseenter", id, () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", id, () => { map.getCanvas().style.cursor = ""; });
  }
}

/**
 * March the route dashes from the unit towards the incident.
 *
 * This is the one piece of ambient motion on the map and it carries information
 * a static dash cannot: which end of the line the unit started from. Honours
 * prefers-reduced-motion, and stops itself when the map goes away.
 */
const DASH_STEPS = [
  [0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1],
  [2.5, 4, 0.5], [3, 4, 0], [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5],
  [0, 2, 3, 2], [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5],
];

function animateRoutes(map) {
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

  let step = 0;
  let last = 0;
  let frame = 0;

  const tick = (now) => {
    frame = requestAnimationFrame(tick);
    if (now - last < 70) return;
    last = now;

    step = (step + 1) % DASH_STEPS.length;
    if (map.getLayer("assignments-line")) {
      map.setPaintProperty("assignments-line", "line-dasharray", DASH_STEPS[step]);
    }

    // One slow breath every ~2.3s on unanswered critical reports.
    if (map.getLayer("incidents-critical")) {
      const phase = (now % 2300) / 2300;
      map.setPaintProperty("incidents-critical", "circle-radius", 14 + phase * 14);
      map.setPaintProperty("incidents-critical", "circle-stroke-opacity", 0.8 * (1 - phase));
    }
  };

  frame = requestAnimationFrame(tick);
  map.once("remove", () => cancelAnimationFrame(frame));
}

/**
 * Build the map with every source registered up front and empty.
 *
 * They are all added here because adding a source later forces MapLibre to
 * reload the style, and the map visibly flashes.
 *
 * IN : el = the container div
 * OUT: maplibregl.Map
 */
export function initMap(el) {
  const map = new maplibregl.Map({
    container: el,
    style: buildBasemapStyle(),
    center: MAP_DEFAULTS.center,
    zoom: MAP_DEFAULTS.zoom,
    maxZoom: 18,
    attributionControl: { compact: true },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

  map.on("load", () => addOverlays(map));
  return map;
}

/**
 * Add our sources and layers on top of whatever basemap is loaded.
 *
 * Called on first load AND after every basemap switch, because setStyle() throws
 * away every source and layer that is not part of the new style.
 */
function addOverlays(map) {
  for (const id of Object.values(SOURCES)) {
    if (!map.getSource(id)) {
      map.addSource(id, { type: "geojson", data: EMPTY });
    }
  }

  // If the basemap is a vector style, its place names are drawn last. Slot our
  // fills and lines above the roads but UNDER those labels, so a flood zone
  // never hides the name of the town it covers. Raster basemaps have no label
  // layer to find, in which case everything simply goes on top.
  const firstLabel = map.getStyle().layers.find((layer) => layer.type === "symbol");

  for (const layer of LAYERS) {
    if (map.getLayer(layer.id)) continue;
    // Pins and their glyphs always sit on top; only fills, lines and heat slot
    // under a vector basemap's place names.
    const goesUnderLabels = layer.type !== "circle" && layer.type !== "symbol";
    map.addLayer(layer, goesUnderLabels ? firstLabel?.id : undefined);
  }

  // Static planning geography: set once, never touched again.
  map.getSource(SOURCES.RISK)?.setData(toRiskGeoJSON());
  map.getSource(SOURCES.SEA)?.setData(toSeaMaskGeoJSON());

  addPopups(map);
  animateRoutes(map);
  applyBasemapTheme(map, document.documentElement.getAttribute("data-theme") ?? "dark");

  // The sources only exist now, so paint whatever the store already holds.
  syncSources(map, useLiveStore.getState());
}

/**
 * Apply one socket event to the live store.
 *
 * IN : event = {type, data}. data is the same row shape that key has inside
 *      GET /api/state. "zone.removed" is just {id} and "kpi.update" is the
 *      whole kpi object.
 */
export function applyDelta(event) {
  const store = useLiveStore.getState();
  const { type, data } = event ?? {};
  if (!type || data == null) return;

  if (type === "kpi.update") {
    store.patch({ kpi: data, t: new Date().toISOString() });
    return;
  }

  const target = EVENT_TO_COLLECTION[type];   // "incident.new" -> "incidents"
  if (!target) return;

  if (type === "zone.removed") {
    store.remove(target, data.id);
    store.patch({ t: new Date().toISOString() });
    return;
  }

  const known = store[target].some((row) => row.id === data.id);
  if (type.endsWith(".update") && !known) {
    // We were told a row changed but we never had it, so we missed an earlier
    // event. Storing this partial row would leave a half-empty object that
    // renders as a pin with no severity and never errors. Refetch instead.
    resyncFullState();
    return;
  }

  store.upsert(target, data);
  store.patch({ t: new Date().toISOString() });
}

// Repaint at most once per animation frame. A burst of fifty deltas should
// repaint once, not fifty times.
let pending = null;      // the newest state waiting to be painted
let frameQueued = false;

/**
 * Paint the two sources no feature hook owns: incidents and shelters.
 *
 * NEVER DROP THE STATE. This used to open with
 *
 *     if (!map || !map.isStyleLoaded()) return;
 *
 * and that early return threw the snapshot away. isStyleLoaded() reports false
 * for stretches while MapLibre is still bringing sources and sprites up, so if
 * the first full sync landed inside that window the incidents and shelters were
 * discarded -- and nothing repainted them, because the only other trigger is the
 * next store change. With a busy socket the next delta covered it up seconds
 * later. On a quiet district the map simply stayed empty: no reports, no
 * shelters, and no error anywhere to say why.
 *
 * Now the snapshot is held and re-applied once the map goes idle.
 */
export function syncSources(map, state) {
  if (!map) return;

  pending = state;
  if (frameQueued) return;
  frameQueued = true;

  requestAnimationFrame(() => {
    frameQueued = false;
    const s = pending;
    if (!s) return;

    if (!map.isStyleLoaded()) {
      // Retry on the next frame. NOT map.once("idle"): animateRoutes keeps a
      // repaint permanently queued, so the map never goes idle and a paint
      // parked on that event would wait forever. frameQueued is already false
      // here, so this re-queues and self-terminates the moment the style is up.
      syncSources(map, s);
      return;
    }

    pending = null;
    map.getSource(SOURCES.INCIDENTS)?.setData(toIncidentGeoJSON(s.incidents));
    map.getSource(SOURCES.SCENES)?.setData(toSceneGeoJSON(s.incidents));
    map.getSource(SOURCES.SHELTERS)?.setData(toShelterGeoJSON(s.shelters));
  });
}

/**
 * Refetch everything and replace the store.
 *
 * Called on first mount and from the socket's onOpen, which fires on every
 * RECONNECT too. Without that the dashboard drifts out of sync after a blip:
 * it still looks fine, and it is wrong.
 */
export function resyncFullState(bbox = null) {
  return fetchState(bbox).then((state) => {
    useLiveStore.getState().hydrate(state);
    return state;
  });
}

export { MAP_DEFAULTS, SEVERITY_COLORS, SOURCES };
