/**
 * Show children only to certain roles. Fully implemented.
 *
 * PROPS:
 *   roles    = [str, ...]   e.g. ["ADMIN", "OPERATOR"]
 *   children = ReactNode
 *   fallback = ReactNode    optional, rendered instead when the role does not
 *                           match. Defaults to nothing.
 *
 * This hides UI. It is NOT security -- the backend re-checks with
 * accounts.permissions.IsOperator on every write. Hiding a button the server
 * would reject anyway is a courtesy, not a control.
 */
import { useAuthStore } from "../store";

export default function RoleGate({ roles, children, fallback = null }) {
  const role = useAuthStore((s) => s.user?.role);
  return roles.includes(role) ? children : fallback;
}
