/**
 * F14 -- drawing the depot-to-shelter flows.
 *
 * Owner: Track 5 - Day 3. First thing to cut if a track slips.
 */
import { SOURCES } from "@/shared/utils/constants";

export function renderFlows(map, flows, depots, shelters) {
  // F14 - Arrows from depot to shelter, width proportional to quantity. Reads
  //       instantly as "where the supplies are going".
  //
  // IN : map      = maplibregl.Map
  //      flows    = [{depot: str, shelter: str, item: str, quantity: int, cost: float}]
  //                 depot/shelter are CODES, not coordinates
  //      depots   = [{code, name, lat, lon}]      -- to resolve the codes
  //      shelters = [{code, name, lat, lon, ...}] -- from the live store
  // OUT: void
  //
  // OUT (the FeatureCollection you build):
  //   {
  //     type: "FeatureCollection",
  //     features: [{
  //       type: "Feature",
  //       geometry: {type: "LineString",
  //                  coordinates: [[depot_lon, depot_lat],
  //                                [shelter_lon, shelter_lat]]},
  //       properties: {item, quantity, width},   // width: interpolate quantity
  //                                              //   onto 1..8 px
  //     }],
  //   }
  //
  // Build a {code -> {lat, lon}} lookup ONCE before the loop. Resolving each
  // code with .find() inside the loop is O(n*m) and it shows on a busy map.
  //
  // map.getSource(SOURCES.SUPPLY).setData(featureCollection)
  throw new Error("TODO renderFlows -- Track 5 - Day 3");
}

export { SOURCES };
