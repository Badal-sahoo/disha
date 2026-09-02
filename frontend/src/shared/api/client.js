/**
 * The one axios instance. Every api.js in every feature folder imports this.
 *
 * Two interceptors do all the auth work, so no feature ever thinks about tokens:
 *   request  -> attaches  Authorization: Bearer <access>
 *   response -> on 401, refreshes ONCE and replays every queued request
 *
 */
import axios from "axios";

import { useAuthStore } from "@/features/auth/store";

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

/** Endpoints that must never carry a Bearer header or trigger a refresh loop. */
const AUTH_FREE = ["/auth/login", "/auth/refresh"];
const isAuthFree = (url = "") => AUTH_FREE.some((p) => url.includes(p));

export const api = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 15000,
});

// ---------------------------------------------------------------------------
// Request interceptor
// ---------------------------------------------------------------------------
api.interceptors.request.use((config) => {
  // IN : config = the outgoing axios request config
  // OUT: the same config, with Authorization added when we hold an access token
  const { access } = useAuthStore.getState();
  if (access && !isAuthFree(config.url)) {
    config.headers.Authorization = `Bearer ${access}`;
  }
  return config;
});

// ---------------------------------------------------------------------------
// Response interceptor -- single-flight refresh
// ---------------------------------------------------------------------------
//
// Why single-flight matters here: the backend runs ROTATE_REFRESH_TOKENS with
// BLACKLIST_AFTER_ROTATION, so a refresh token is valid exactly once. The
// dashboard fires several requests at a time (state, plan, kpi, resources). If
// each 401 kicked off its own refresh, the first would rotate the token and the
// rest would present a blacklisted one -- and the user gets bounced to /login
// for no reason. So: the FIRST 401 starts a refresh, everyone else waits on
// that same promise.
let refreshPromise = null;

/**
 * Exchange the stored refresh token for a new pair.
 *
 * IN : --  (reads useAuthStore.getState().refresh)
 * OUT: Promise<string>  the new access token
 *      rejects when there is no refresh token, or the server refuses it
 *
 * Uses a BARE axios call, not `api`, so it cannot recurse through this
 * interceptor if the refresh itself comes back 401.
 */
function requestRefresh() {
  const { refresh } = useAuthStore.getState();
  if (!refresh) return Promise.reject(new Error("no refresh token"));

  return axios
    .post(`${API_URL}/auth/refresh`, { refresh }, { timeout: 15000 })
    .then(({ data }) => {
      // IN : data = {access: str, refresh: str}   -- refresh is rotated
      // OUT: the new access token, already persisted to the store
      useAuthStore.getState().setTokens({
        access: data.access,
        refresh: data.refresh ?? refresh,
      });
      return data.access;
    });
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const { response, config } = error;

    // Not an auth problem, a login/refresh call, or already retried once.
    if (
      !response ||
      response.status !== 401 ||
      !config ||
      config._retried ||
      isAuthFree(config.url)
    ) {
      return Promise.reject(error);
    }
    config._retried = true;

    if (!refreshPromise) {
      refreshPromise = requestRefresh().finally(() => {
        refreshPromise = null;
      });
    }

    return refreshPromise
      .then((access) => {
        config.headers.Authorization = `Bearer ${access}`;
        return api(config); // replay the original request
      })
      .catch((refreshError) => {
        // Refresh failed for real -- the session is over.
        useAuthStore.getState().logout();
        if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
          window.location.assign("/login");
        }
        return Promise.reject(refreshError);
      });
  }
);

/**
 * GET an endpoint that returns a list, and always hand back an array.
 *
 * Django REST Framework paginates its list views, so those come back as
 * {count, next, previous, results} rather than a bare array. Endpoints built on
 * a plain APIView are NOT paginated and return the array directly. This copes
 * with both, so no caller has to know which kind it is talking to -- forgetting
 * that is what makes a component crash with "x is not iterable".
 *
 * IN : url = str, config = axios config (params, etc.)
 * OUT: Promise<Array>
 */
export function getList(url, config) {
  return api.get(url, config).then(({ data }) => unwrapList(data));
}

/** The shape-handling half of getList, split out so it can be tested directly. */
export function unwrapList(data) {
  if (Array.isArray(data)) return data;
  return data?.results ?? [];
}

/**
 * Normalise any axios failure into something a component can render.
 *
 * IN : error = the axios error object
 * OUT: {status: number|null, code: str, detail: str, fields: obj}
 *      code   -- "not_implemented" when a backend service is unfinished,
 *                "invalid" for a 400, "network" when the request never landed
 *      fields -- DRF's per-field validation errors, {} when there are none
 */
export function toApiError(error) {
  const data = error?.response?.data ?? {};
  const { detail, code, ...fields } = typeof data === "object" ? data : {};
  return {
    status: error?.response?.status ?? null,
    code: code ?? (error?.response ? "error" : "network"),
    detail: detail ?? error?.message ?? "Request failed",
    fields,
  };
}
