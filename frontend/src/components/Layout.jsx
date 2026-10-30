import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { AlertTriangle, CheckCircle2, Files, ListChecks, LogOut, Menu, PanelLeftClose, Shield, ShieldCheck, X } from "lucide-react";
import ErrorBoundary from "./ErrorBoundary.jsx";
import { useAuth, useBackend, useNotice } from "../state.jsx";

const mobileQuery = window.matchMedia("(max-width: 800px)");  // same breakpoint as index.css

const NAVIGATION = [
  { to: "/documents", label: "Documents", icon: Files },
  { to: "/checks", label: "Automated checks", icon: ListChecks },
];

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [isMobile, setIsMobile] = useState(mobileQuery.matches);
  const { user, logout } = useAuth();
  const { online } = useBackend();
  const { notice, dismiss } = useNotice();
  const location = useLocation();

  useEffect(() => {
    const update = () => setIsMobile(mobileQuery.matches);
    mobileQuery.addEventListener("change", update);
    return () => mobileQuery.removeEventListener("change", update);
  }, []);

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      {mobileNav && <button className="mobile-backdrop" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}
      {/* Off-screen on mobile while closed: inert keeps it out of the tab order and screen readers. */}
      <aside id="sidebar" className={`sidebar ${mobileNav ? "mobile-open" : ""}`} inert={isMobile && !mobileNav}>
        <div className="brand">
          <div className="brand-mark"><ShieldCheck size={22} /></div>
          <div className="brand-text">SafeSOP<span>AI</span><small>Controlled SOP revision</small></div>
          <button className="icon-button sidebar-collapse" onClick={() => setCollapsed(!collapsed)} aria-label="Toggle sidebar"><PanelLeftClose size={17} /></button>
        </div>
        <nav aria-label="Main">
          <div className="nav-group">
            {NAVIGATION.map((item) => (
              <NavLink key={item.to} to={item.to} onClick={() => setMobileNav(false)} className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`}>
                <item.icon size={18} /><span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </nav>
        <div className="sidebar-bottom">
          <div className={`storage-card ${online ? "online" : "offline"}`}><div className="storage-icon"><Shield size={17} /></div><strong>Originals never change</strong><p>Every draft is traced back to the PDF it came from.</p><small>{online ? "Backend connected" : "Backend offline"}</small></div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left"><button className="icon-button mobile-menu" onClick={() => setMobileNav(true)} aria-label="Open navigation" aria-expanded={mobileNav} aria-controls="sidebar"><Menu size={20} /></button></div>
          <div className="topbar-right">
            {user && <span className="user-chip"><strong>{user.username}</strong> · {user.role}</span>}
            <button className="btn btn-secondary" onClick={logout}><LogOut size={15} /> Sign out</button>
          </div>
        </header>

        <div className="page-content">
          <ErrorBoundary key={location.pathname}><Outlet /></ErrorBoundary>
          <footer className="app-footer"><span><ShieldCheck size={14} /> SafeSOP AI prototype</span><span>AI drafts are never safety-approved without a qualified reviewer.</span></footer>
        </div>
      </main>
      {notice && <div className={`toast ${notice.tone === "error" ? "toast-error" : ""}`} role={notice.tone === "error" ? "alert" : "status"}><div className="toast-icon">{notice.tone === "error" ? <AlertTriangle size={17} /> : <CheckCircle2 size={17} />}</div><span>{notice.message}</span><button onClick={dismiss} aria-label="Dismiss notification"><X size={15} /></button></div>}
    </div>
  );
}
