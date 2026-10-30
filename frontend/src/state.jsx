// App-wide state, split by concern. Pages read only what they need through these hooks.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { checkBackend, getEvaluationStatus, getMe, getToken, login as apiLogin, setToken, setUnauthorizedHandler } from "./api.js";

const HEALTH_POLL_MS = 15000;

// ---- auth: who is signed in ----
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(Boolean(getToken()));
  const navigate = useNavigate();
  const location = useLocation();
  const locationRef = useRef(location);
  useEffect(() => { locationRef.current = location; }, [location]);

  useEffect(() => {
    // Any 401 means the session ended: back to the sign-in page, then return here.
    setUnauthorizedHandler(() => {
      setUser(null);
      if (locationRef.current.pathname !== "/login") navigate("/login", { state: { from: locationRef.current } });
    });
    if (!getToken()) return;
    getMe().then(setUser).catch(() => setUser(null)).finally(() => setChecking(false));
  }, [navigate]);

  const login = useCallback(async (username, password) => setUser(await apiLogin(username, password)), []);
  const logout = useCallback(() => { setToken(null); setUser(null); navigate("/login"); }, [navigate]);
  const can = useCallback((role) => Boolean(user && (user.role === role || user.role === "admin")), [user]);

  return <AuthContext.Provider value={{ user, checking, login, logout, can }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

// ---- notices: one toast at a time ----
const NoticeContext = createContext(null);

export function NoticeProvider({ children }) {
  const [notice, setNotice] = useState(null);
  const timer = useRef(null);
  const show = useCallback((message, tone = "success") => {
    setNotice({ message, tone });
    window.clearTimeout(timer.current);  // a new toast gets its own full 6 seconds
    timer.current = window.setTimeout(() => setNotice(null), 6000);
  }, []);
  const dismiss = useCallback(() => setNotice(null), []);
  return <NoticeContext.Provider value={{ notice, show, dismiss }}>{children}</NoticeContext.Provider>;
}

export const useNotice = () => useContext(NoticeContext);

// ---- backend: polled so a server started (or restarted) later is picked up ----
const BackendContext = createContext(null);

export function BackendProvider({ children }) {
  const [status, setStatus] = useState({ online: false, evaluatorVersion: "" });
  useEffect(() => {
    let online = false;
    async function poll() {
      try {
        await checkBackend();
        if (!online) {
          const { evaluator_version: evaluatorVersion } = await getEvaluationStatus();
          setStatus({ online: true, evaluatorVersion });
        }
        online = true;
      } catch {
        online = false;
        setStatus((current) => ({ ...current, online: false }));
      }
    }
    poll();
    const timer = window.setInterval(poll, HEALTH_POLL_MS);
    return () => window.clearInterval(timer);
  }, []);
  return <BackendContext.Provider value={status}>{children}</BackendContext.Provider>;
}

export const useBackend = () => useContext(BackendContext);

// ---- data loading ----
// Runs `load` whenever `deps` change. A response that arrives after the deps changed again
// is dropped, so a slow reply can never fill the screen with another item's data.
export function useResource(load, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let current = true;
    setState((previous) => ({ ...previous, loading: true, error: null }));
    load()
      .then((data) => { if (current) setState({ data, error: null, loading: false }); })
      .catch((error) => { if (current) setState({ data: null, error, loading: false }); });
    return () => { current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((value) => value + 1), []);
  return { ...state, reload };
}

// One <h1> per view and a matching tab title.
export function useTitle(title) {
  useEffect(() => { document.title = `${title} · SafeSOP AI`; }, [title]);
}
