/**
 * App shell. Fully wired.
 *
 * useSyncUser re-reads GET /api/auth/me on boot, so a hard refresh restores the
 * role gate from the server rather than trusting whatever localStorage kept.
 */
import { BrowserRouter } from "react-router-dom";

import { useSyncUser } from "@/features/auth/hooks";

import AppRoutes from "./routes";

function Bootstrap() {
  const { loading } = useSyncUser();
  if (loading) return <div className="boot">Restoring session</div>;
  return <AppRoutes />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Bootstrap />
    </BrowserRouter>
  );
}
