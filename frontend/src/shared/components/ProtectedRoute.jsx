/**
 * Route guard. Fully implemented.
 *
 * Redirects to /login when there is no token, and optionally gates on role.
 * This is UX, not security -- the backend re-checks every write with
 * accounts.permissions.IsOperator.
 */
import { Navigate, useLocation } from "react-router-dom";

import { useAuthStore } from "@/features/auth/store";

/**
 * PROPS:
 *   children = ReactNode
 *   roles    = [str, ...] | null   e.g. ["ADMIN", "OPERATOR"]; null = any
 *                                  authenticated user
 */
export default function ProtectedRoute({ children, roles = null }) {
  const access = useAuthStore((s) => s.access);
  const role = useAuthStore((s) => s.user?.role);
  const location = useLocation();

  if (!access) return <Navigate to="/login" replace state={{ from: location.pathname }} />;

  // `role` is briefly undefined between a hard reload and useSyncUser
  // resolving. Let it through -- bouncing on a not-yet-known role logs the
  // operator out on every refresh.
  if (roles && role && !roles.includes(role)) {
    return <div className="error-page">Your role ({role}) cannot open this screen.</div>;
  }

  return children;
}
