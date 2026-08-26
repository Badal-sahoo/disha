/**
 * Route table. Fully wired.
 *
 * Only two screens exist: the login form and the ops dashboard. Every dashboard
 * feature is a panel inside DashboardPage, not a route of its own -- an ops
 * room reads one screen, it does not navigate.
 */
import { Navigate, Route, Routes } from "react-router-dom";

import { LoginPage } from "@/features/auth";
import { DashboardPage } from "@/features/map";
import ProtectedRoute from "@/shared/components/ProtectedRoute";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute roles={["ADMIN", "OPERATOR"]}>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
