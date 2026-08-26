/**
 * Auth state: the two tokens and who is logged in.
 *
 * Fully implemented. Lives in the auth FEATURE folder (not shared/) because it
 * belongs to auth -- shared/api/client.js is the one place outside this folder
 * that reaches in, and it does so through the public getState() surface only.
 */
import { create } from "zustand";

const STORAGE_KEY = "ps05.auth";

/**
 * Read the persisted session back on a hard refresh.
 *
 * IN : --
 * OUT: {access: str|null, refresh: str|null, user: obj|null}
 *      Everything null when storage is empty or unreadable (private windows
 *      throw on localStorage access -- never let that crash the app).
 */
function rehydrate() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { access: null, refresh: null, user: null };
    const saved = JSON.parse(raw);
    return {
      access: saved.access ?? null,
      refresh: saved.refresh ?? null,
      user: saved.user ?? null,
    };
  } catch {
    return { access: null, refresh: null, user: null };
  }
}

function persist(state) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ access: state.access, refresh: state.refresh, user: state.user })
    );
  } catch {
    /* private window -- the session just does not survive a reload */
  }
}

export const useAuthStore = create((set, get) => ({
  ...rehydrate(),

  /**
   * Store the pair returned by POST /api/auth/login or /api/auth/refresh.
   *
   * IN : {access: str, refresh: str}
   * OUT: void
   */
  setTokens: ({ access, refresh }) => {
    set({ access, refresh });
    persist(get());
  },

  /**
   * Store the identity half of a login response, or GET /api/auth/me.
   *
   * IN : user = {
   *        id:            int,
   *        username:      str,
   *        role:          str,       // "ADMIN" | "OPERATOR" | "RESPONDER"
   *        resource_id:   int|null,
   *        resource_code: str|null,
   *        phone:         str,
   *      }
   * OUT: void
   */
  setUser: (user) => {
    set({ user });
    persist(get());
  },

  /**
   * Clear everything. Called by the logout button AND by the axios interceptor
   * when a refresh finally fails.
   *
   * IN : --
   * OUT: void
   */
  logout: () => {
    set({ access: null, refresh: null, user: null });
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  },

  // --- derived reads, so components never poke at raw token strings ---

  /** OUT: bool -- do we hold an access token at all? */
  isAuthenticated: () => Boolean(get().access),

  /** OUT: str|null -- "ADMIN" | "OPERATOR" | "RESPONDER" */
  role: () => get().user?.role ?? null,

  /**
   * IN : roles = [str, ...]   e.g. ["ADMIN", "OPERATOR"]
   * OUT: bool                 -- true when the current role is in the list
   */
  hasRole: (roles) => roles.includes(get().user?.role),
}));
