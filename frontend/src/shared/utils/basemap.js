/**
 * The basemap under everything else. One standard map, always.
 *
 * These are RASTER tiles, not a vector style, for two reasons:
 *   1. They go to zoom 19. The vector styles stop at 14 and the tile server
 *      returns 400 above that, which is why zooming in went blank.
 *   2. Ordinary road colours and place names -- the map people recognise.
 *
 * The PROVIDER is configurable, because they change their terms. CARTO used to
 * serve basemaps.cartocdn.com without a key and now stamps "API KEY REQUIRED"
 * diagonally across every tile. Rather than hardcode the next one, both the URL
 * and its attribution come from the environment, so swapping provider -- keyed
 * or keyless -- is an .env edit and no code change.
 *
 * Default: the OpenStreetMap standard tiles. No key, no signup, zoom 19.
 * See frontend/.env.example for the keyed alternatives and their trade-offs.
 */
const TILE_SIZE = 256;
export const MAX_ZOOM = 19;

const DEFAULT_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const DEFAULT_ATTRIBUTION =
  '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap</a> contributors';

/* Attribution is not decoration -- every provider below requires its own, and
   swapping the URL without the credit breaks their terms. Keep the pair together. */
const TILES = import.meta.env.VITE_MAP_TILE_URL || DEFAULT_TILES;
const ATTRIBUTION = import.meta.env.VITE_MAP_ATTRIBUTION || DEFAULT_ATTRIBUTION;

/**
 * The MapLibre style for the basemap.
 *
 * The background layer under the tiles matters: without it you see white
 * flashes in the gaps while tiles are still loading.
 */
export function buildBasemapStyle() {
  return {
    version: 8,
    sources: {
      basemap: {
        type: "raster",
        tiles: [TILES],
        tileSize: TILE_SIZE,
        maxzoom: MAX_ZOOM,
        attribution: ATTRIBUTION,
      },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": "#f5f3f0" } },
      { id: "basemap", type: "raster", source: "basemap" },
    ],
  };
}
