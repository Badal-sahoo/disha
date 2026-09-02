/**
 * Everything that changes between one laptop and the next.
 *
 * Values come from App/.env. Expo only exposes variables prefixed
 * EXPO_PUBLIC_ to the bundle, and they are inlined at BUILD time -- so after
 * editing .env you must restart the dev server with a cleared cache:
 *
 *   npx expo start --clear
 *
 * The fallbacks below are only so a fresh clone starts without crashing. They
 * are not useful values; set the real ones in .env.
 */

/**
 * A phone cannot reach "localhost" -- that is the phone itself. This has to be
 * the LAN address of the machine running daphne, and that same address must be
 * in ALLOWED_HOSTS in backend/.env or every request comes back 400.
 *
 *   ipconfig getifaddr en0        # macOS, prints e.g. 192.168.1.24
 */
export const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE ?? 'http://192.168.1.24:8000/api';

/**
 * The number the Android SMS gateway listens on.
 *
 * On this path the victim's phone never talks to the server: it texts the
 * gateway, and the gateway forwards to POST /api/sms. That indirection is the
 * whole point -- it works with no data connection at all.
 */
export const SMS_GATEWAY_NUMBER =
  process.env.EXPO_PUBLIC_SMS_GATEWAY_NUMBER ?? '+919999000000';

/**
 * The account reports are filed under.
 *
 * POST /api/reports is behind IsAuthenticated and a drowning villager has no
 * login, so the app carries one shared, low-privilege account.
 *
 * EXPO_PUBLIC_ variables are inlined into the JS bundle, so this password ships
 * inside the APK in readable form. That is acceptable for a demo and not for
 * production: the real fixes are a device-registration handshake, or opening
 * the endpoint with a hard rate limit. Do not skip this before going public.
 */
export const APP_ACCOUNT = {
  username: process.env.EXPO_PUBLIC_APP_USERNAME ?? 'operator1',
  password: process.env.EXPO_PUBLIC_APP_PASSWORD ?? 'demo1234',
};

/**
 * Pretend to be somewhere else.
 *
 * The seeded district is Puri. Your phone is not in Puri, so a real GPS fix
 * drops the pin hundreds of kilometres off the map, no unit can reach it, and
 * the demo shows nothing. Setting these makes the app report the given
 * position instead of the one the GPS returns.
 *
 * This is a DEMO AID and it announces itself in the UI -- the status line says
 * "demo location" so nobody watching is misled into thinking it is a real fix.
 * Leave both unset for real behaviour.
 */
const demoLat = Number(process.env.EXPO_PUBLIC_DEMO_LAT);
const demoLon = Number(process.env.EXPO_PUBLIC_DEMO_LON);
export const DEMO_LOCATION =
  Number.isFinite(demoLat) && Number.isFinite(demoLon) && demoLat !== 0 && demoLon !== 0
    ? { lat: demoLat, lon: demoLon }
    : null;

/** Give up on a request after this and offer the SMS path instead. */
export const REQUEST_TIMEOUT_MS = Number(
  process.env.EXPO_PUBLIC_REQUEST_TIMEOUT_MS ?? 8000,
);

/** How often to ask the server what happened to a report we filed. */
export const TRACK_POLL_MS = Number(
  process.env.EXPO_PUBLIC_TRACK_POLL_MS ?? 5000,
);
