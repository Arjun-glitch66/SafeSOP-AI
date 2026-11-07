import { Navigate, Route, Routes, useLocation } from "react-router";
import Layout from "./components/Layout.jsx";
import { useAuth } from "./state.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import DocumentsPage from "./pages/DocumentsPage.jsx";
import DocumentPage from "./pages/DocumentPage.jsx";
import VersionPage from "./pages/VersionPage.jsx";
import ReviewPage from "./pages/ReviewPage.jsx";
import ChecksPage from "./pages/ChecksPage.jsx";
import UsersPage from "./pages/UsersPage.jsx";
import AuditPage from "./pages/AuditPage.jsx";
import AccountPage from "./pages/AccountPage.jsx";

// Every route except /login needs a signed-in user; the server checks roles again.
function RequireAuth({ children }) {
  const { user, checking } = useAuth();
  const location = useLocation();
  if (checking) return <p className="small-note page-loading">Checking sign-in…</p>;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return children;
}

// Admin pages: hidden from the menu for others, and the API refuses their calls anyway (403).
function RequireAdmin({ children }) {
  const { user } = useAuth();
  return user?.role === "admin" ? children : <Navigate to="/dashboard" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/documents/:documentId" element={<DocumentPage />} />
        <Route path="/versions/:versionId" element={<VersionPage />} />
        <Route path="/versions/:versionId/review" element={<ReviewPage />} />
        <Route path="/checks" element={<ChecksPage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="/users" element={<RequireAdmin><UsersPage /></RequireAdmin>} />
        <Route path="/audit" element={<RequireAdmin><AuditPage /></RequireAdmin>} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
