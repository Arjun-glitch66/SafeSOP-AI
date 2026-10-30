import { Navigate, Route, Routes, useLocation } from "react-router";
import Layout from "./components/Layout.jsx";
import { useAuth } from "./state.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import DocumentsPage from "./pages/DocumentsPage.jsx";
import DocumentPage from "./pages/DocumentPage.jsx";
import VersionPage from "./pages/VersionPage.jsx";
import ReviewPage from "./pages/ReviewPage.jsx";
import ChecksPage from "./pages/ChecksPage.jsx";

// Every route except /login needs a signed-in user; the server checks roles again.
function RequireAuth({ children }) {
  const { user, checking } = useAuth();
  const location = useLocation();
  if (checking) return <p className="small-note page-loading">Checking sign-in…</p>;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Navigate to="/documents" replace />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/documents/:documentId" element={<DocumentPage />} />
        <Route path="/versions/:versionId" element={<VersionPage />} />
        <Route path="/versions/:versionId/review" element={<ReviewPage />} />
        <Route path="/checks" element={<ChecksPage />} />
        <Route path="*" element={<Navigate to="/documents" replace />} />
      </Route>
    </Routes>
  );
}
