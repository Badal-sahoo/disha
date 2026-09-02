/**
 * Flood risk, drawn as a continuous gradient rather than as zones with edges.
 *
 * WHY NOT POLYGONS. The first version of this drew three bands as filled
 * rings -- red, amber, green -- and it read as a political map: three flat
 * shapes with hard borders, as if a village 100 m inside a line were safe and
 * its neighbour 100 m outside were not. Flood risk does not work like that. It
 * falls off smoothly with distance from the water, and the way an atlas shows
 * that is a continuous wash: deep red at the shore bleeding through orange and
 * yellow into green, with no line anywhere.
 *
 * HOW. The shoreline is sampled into a dense run of points and handed to a
 * MapLibre heatmap layer. Density is highest on the coast and decays with
 * distance, so the colour ramp below turns "how far inland am I" into the
 * gradient directly -- no bands, no edges, and it stays smooth at every zoom.
 *
 * This is PLANNING GEOGRAPHY, not live state: it is the same every day, it has
 * no backend, and it is set once when the map loads. Not to be confused with
 * the incident heatmap that used to live here -- that showed where reports had
 * clustered in the last hour and went blank on a quiet district, which is the
 * opposite of what you plan an evacuation around.
 *
 * ponytail: distance-from-shore is the only input. Real inundation also depends
 * on elevation and drainage; swap in OSDMA's vulnerability raster if it becomes
 * available and keep the same ramp.
 */

/**
 * The REAL Puri shoreline, from OpenStreetMap `natural=coastline`.
 *
 * 98 points, ~800 m apart, running 101 km from the Chilika mouth in the
 * south-west to the Devi river mouth at Astaranga in the north-east.
 *
 * This was five hand-picked points, and five was not enough for two reasons:
 * the gradient anchored to a shore that was kilometres off the real one, and
 * the sea mask built from the same five points cut a visible straight diagonal
 * across the bay. A coarse coastline is fine for a heat gradient and useless as
 * a clipping edge.
 *
 * Re-fetch with:
 *   [out:json];way["natural"="coastline"](19.40,85.00,20.30,86.60);out geom;
 * then keep the SEAWARD shore only -- around the Chilika spit two shorelines
 * run parallel and taking both reports a 300 km coast for a 101 km shore.
 */
const COASTLINE = [
  [19.7089, 85.6007],
  [19.7136, 85.6113],
  [19.7168, 85.6190],
  [19.7206, 85.6267],
  [19.7250, 85.6360],
  [19.7306, 85.6482],
  [19.7350, 85.6581],
  [19.7390, 85.6671],
  [19.7422, 85.6746],
  [19.7454, 85.6822],
  [19.7483, 85.6902],
  [19.7513, 85.6984],
  [19.7541, 85.7065],
  [19.7568, 85.7144],
  [19.7594, 85.7220],
  [19.7623, 85.7302],
  [19.7652, 85.7386],
  [19.7678, 85.7463],
  [19.7707, 85.7548],
  [19.7732, 85.7621],
  [19.7762, 85.7704],
  [19.7791, 85.7789],
  [19.7823, 85.7862],
  [19.7852, 85.7945],
  [19.7880, 85.8030],
  [19.7903, 85.8110],
  [19.7930, 85.8196],
  [19.7962, 85.8303],
  [19.7988, 85.8391],
  [19.8009, 85.8466],
  [19.8036, 85.8564],
  [19.8056, 85.8638],
  [19.8085, 85.8743],
  [19.8110, 85.8838],
  [19.8138, 85.8951],
  [19.8156, 85.9025],
  [19.8181, 85.9130],
  [19.8210, 85.9224],
  [19.8238, 85.9305],
  [19.8260, 85.9381],
  [19.8280, 85.9466],
  [19.8297, 85.9549],
  [19.8313, 85.9635],
  [19.8328, 85.9715],
  [19.8348, 85.9831],
  [19.8365, 85.9916],
  [19.8379, 85.9993],
  [19.8398, 86.0090],
  [19.8419, 86.0195],
  [19.8440, 86.0301],
  [19.8458, 86.0391],
  [19.8485, 86.0503],
  [19.8507, 86.0586],
  [19.8527, 86.0666],
  [19.8552, 86.0759],
  [19.8584, 86.0864],
  [19.8610, 86.0960],
  [19.8643, 86.1090],
  [19.8676, 86.1210],
  [19.8707, 86.1315],
  [19.8731, 86.1398],
  [19.8756, 86.1482],
  [19.8779, 86.1557],
  [19.8813, 86.1665],
  [19.8841, 86.1754],
  [19.8870, 86.1849],
  [19.8899, 86.1940],
  [19.8930, 86.2032],
  [19.8968, 86.2143],
  [19.8996, 86.2221],
  [19.9031, 86.2314],
  [19.9074, 86.2381],
  [19.9118, 86.2465],
  [19.9155, 86.2548],
  [19.9195, 86.2623],
  [19.9236, 86.2707],
  [19.9275, 86.2788],
  [19.9307, 86.2862],
  [19.9337, 86.2940],
  [19.9369, 86.3025],
  [19.9395, 86.3102],
  [19.9425, 86.3193],
  [19.9447, 86.3270],
  [19.9476, 86.3374],
  [19.9500, 86.3465],
  [19.9518, 86.3540],
  [19.9542, 86.3624],
  [19.9581, 86.3708],
  [19.9635, 86.3807],
  [19.9619, 86.3882],
  [19.9668, 86.3943],
  [19.9713, 86.4036],
  [19.9772, 86.4118],
  [19.9963, 86.4141],
  [20.0327, 86.4233],
  [20.0463, 86.4303],
  [20.0552, 86.4342],
  [20.0659, 86.4421],
];

/** Points every ~1 km along the coast, so the wash has no gaps or hot spots. */
function sampleCoast(stepKm = 1) {
  const KM_LAT = 111.32;
  const KM_LON = 104.66; // at ~19.9 N
  const points = [];

  for (let i = 0; i < COASTLINE.length - 1; i += 1) {
    const [aLat, aLon] = COASTLINE[i];
    const [bLat, bLon] = COASTLINE[i + 1];
    const km = Math.hypot((bLat - aLat) * KM_LAT, (bLon - aLon) * KM_LON);
    const steps = Math.max(1, Math.round(km / stepKm));
    for (let s = 0; s < steps; s += 1) {
      const t = s / steps;
      points.push([aLat + (bLat - aLat) * t, aLon + (bLon - aLon) * t]);
    }
  }
  points.push(COASTLINE[COASTLINE.length - 1]);
  return points;
}

/** OUT: FeatureCollection of coastline samples, for the risk heatmap layer. */
export function toRiskGeoJSON() {
  return {
    type: "FeatureCollection",
    features: sampleCoast().map(([lat, lon]) => ({
      type: "Feature",
      properties: {},
      // GeoJSON is [lon, lat]; everything else in this project is (lat, lon).
      geometry: { type: "Point", coordinates: [lon, lat] },
    })),
  };
}

/**
 * Low density (far inland) at the bottom, high (on the shore) at the top.
 *
 * Transparent at the very bottom so the wash ends by fading out rather than
 * stopping at a green line -- which would reintroduce exactly the edge this
 * whole approach exists to avoid.
 */
export const RISK_RAMP = [
  0.00, "rgba(47, 169, 138, 0)",
  0.12, "rgba(47, 169, 138, 0.30)",    // green -- inland, wind not water
  0.32, "rgba(160, 190, 70, 0.36)",
  0.48, "rgba(242, 193, 78, 0.42)",    // yellow
  0.64, "rgba(237, 162, 59, 0.48)",    // orange
  0.82, "rgba(209, 76, 40, 0.54)",
  1.00, "rgba(176, 32, 32, 0.62)",     // red -- the surge belt
];

/**
 * The sea, as a polygon, so the wash can be clipped off it.
 *
 * A heatmap radiates in every direction from its points, so a gradient anchored
 * on the shoreline fades inland AND out to sea at the same rate -- which painted
 * the Bay of Bengal the same green the layer uses for "safe, inland". That is
 * not a cosmetic problem: green over open water is a flood-risk map saying the
 * ocean is the safest place in the district.
 *
 * There is no way to make a MapLibre heatmap one-sided, so the seaward half is
 * covered instead: this polygon runs along the coast and out into the bay, and
 * is drawn over the wash in the basemap's own water tone.
 */
export function toSeaMaskGeoJSON() {
  const KM_LAT = 111.32;
  const KM_LON = 104.66;
  // Perpendicular to the coast, pointing out to sea (the coast trends NE, so
  // seaward is SE) -- the opposite of the inland direction.
  const bearing = (150 * Math.PI) / 180;
  const outKm = 90;
  const seaward = COASTLINE.map(([lat, lon]) => [
    lat + (outKm * Math.cos(bearing)) / KM_LAT,
    lon + (outKm * Math.sin(bearing)) / KM_LON,
  ]);
  // Along the shore, then back along the offshore edge. Extended past both ends
  // so the mask never stops short and leaves a wedge of green water.
  const ring = [...COASTLINE, ...seaward.reverse()];
  ring.push(ring[0]);
  return {
    type: "FeatureCollection",
    features: [{
      type: "Feature",
      properties: {},
      geometry: { type: "Polygon", coordinates: [ring.map(([lat, lon]) => [lon, lat])] },
    }],
  };
}

/** What the legend says, so the colours are readable without guessing. */
export const RISK_LEGEND = [
  { color: "#b02020", label: "surge belt" },
  { color: "#eda23b", label: "flood plain" },
  { color: "#2fa98a", label: "inland" },
];
