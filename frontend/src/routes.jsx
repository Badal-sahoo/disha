/**
 * Route table.
 *
 * Four sections behind one persistent shell. Layout is the PARENT route rather
 * than something each page wraps itself in -- that is what keeps it mounted
 * across navigation, and with it the ops socket.
 */
import { Navigate, Route, Routes } from "react-router-dom";

import IncomingPage from "@/features/alerts/pages/IncomingPage";
import LoginPage from "@/features/auth/pages/LoginPage";
import DispatchPage from "@/features/dispatch/pages/DispatchPage";
import DashboardPage from "@/features/map/pages/DashboardPage";
import ResourcesPage from "@/features/resources/pages/ResourcesPage";
import Layout from "@/shared/components/Layout";
import ProtectedRoute from "@/shared/components/ProtectedRoute";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <ProtectedRoute roles={["ADMIN", "OPERATOR"]}>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/incoming" element={<IncomingPage />} />
        <Route path="/dispatch" element={<DispatchPage />} />
        <Route path="/resources" element={<ResourcesPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
