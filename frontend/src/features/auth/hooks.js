/**
 * auth hooks. Fully implemented -- this is the wiring the whole app gates on.
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { toApiError } from "@/shared/api/client";

import { fetchMe, login as loginRequest } from "./api";
import { useAuthStore } from "./store";

/**
 * Everything a component needs to log in, log out, and read who is here.
 *
 * IN : --
 * OUT: {
 *        user:            obj|null,   // {id, username, role, resource_id, ...}
 *        role:            str|null,
 *        isAuthenticated: bool,
 *        pending:         bool,       // a login request is in flight
 *        error:           obj|null,   // toApiError() shape
 *        signIn:   (username, password) => Promise<user>,
 *        signOut:  () => void,
 *      }
 */
export function useAuth() {
  const navigate = useNavigate();
  const { user, access, setTokens, setUser, logout } = useAuthStore();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const signIn = useCallback(
    async (username, password) => {
      setPending(true);
      setError(null);
      try {
        const data = await loginRequest(username, password);
        setTokens({ access: data.access, refresh: data.refresh });
        const me = {
          id: data.user_id,
          username: data.username,
          role: data.role,
          resource_id: data.resource_id,
        };
        setUser(me);
        return me;
      } catch (e) {
        setError(toApiError(e));
        throw e;
      } finally {
        setPending(false);
      }
    },
    [setTokens, setUser]
  );

  const signOut = useCallback(() => {
    logout();
    navigate("/login", { replace: true });
  }, [logout, navigate]);

  return {
    user,
    role: user?.role ?? null,
    isAuthenticated: Boolean(access),
    pending,
    error,
    signIn,
    signOut,
  };
}

/**
 * Refresh the stored identity from the server on mount.
 *
 * Why it exists: the login response carries role and resource_id so the first
 * paint needs no round trip, but on a hard reload we only have what
 * localStorage kept. This re-reads the truth, and a 401 here means the stored
 * refresh token is dead -- the interceptor will bounce to /login on its own.
 *
 * IN : --
 * OUT: {loading: bool}
 */
export function useSyncUser() {
  const { access, setUser } = useAuthStore();
  const [loading, setLoading] = useState(Boolean(access));

  useEffect(() => {
    if (!access) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    fetchMe()
      .then((me) => !cancelled && setUser(me))
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [access, setUser]);

  return { loading };
}
