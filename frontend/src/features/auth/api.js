/**
 * auth feature -- endpoint wrappers. Fully implemented.
 */
import { api } from "@/shared/api/client";

/**
 * POST /api/auth/login
 *
 * IN : {username: str, password: str}
 * OUT: Promise<{
 *        access:      str,       // JWT, 60 min
 *        refresh:     str,       // JWT, 7 days, rotated on every refresh
 *        user_id:     int,
 *        username:    str,
 *        role:        str,       // "ADMIN" | "OPERATOR" | "RESPONDER"
 *        resource_id: int|null,  // the unit a RESPONDER drives
 *      }>
 * THROWS: 401 when the credentials are wrong
 */
export function login(username, password) {
  return api.post("/auth/login", { username, password }).then((r) => r.data);
}

/**
 * POST /api/auth/refresh
 *
 * IN : refresh = str
 * OUT: Promise<{access: str, refresh: str}>
 *
 * NOTE: components should never call this. shared/api/client.js refreshes
 * automatically on a 401, single-flight, and replays the original request.
 * It is exported only so the interceptor has one canonical definition to point
 * at, and for tests.
 */
export function refreshTokens(refresh) {
  return api.post("/auth/refresh", { refresh }).then((r) => r.data);
}

/**
 * GET /api/auth/me
 *
 * IN : -- (Bearer header added by the interceptor)
 * OUT: Promise<{
 *        id:            int,
 *        username:      str,
 *        role:          str,       // "ADMIN" | "OPERATOR" | "RESPONDER"
 *        resource_id:   int|null,
 *        resource_code: str|null,  // "BOAT-04"
 *        phone:         str,
 *      }>
 * THROWS: 401 when the token is missing or expired
 */
export function fetchMe() {
  return api.get("/auth/me").then((r) => r.data);
}
