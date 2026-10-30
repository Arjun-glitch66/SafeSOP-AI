import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { LogIn, ShieldCheck } from "lucide-react";
import { useAuth, useBackend, useTitle } from "../state.jsx";

export default function LoginPage() {
  useTitle("Sign in");
  const { user, login } = useAuth();
  const { online } = useBackend();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const back = location.state?.from?.pathname || "/documents";

  if (user) return <Navigate to={back} replace />;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(username, password);
      navigate(back, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <form className="panel login-card" onSubmit={submit}>
        <div className="brand"><div className="brand-mark"><ShieldCheck size={22} /></div><div className="brand-text">SafeSOP<span>AI</span><small>Controlled SOP revision</small></div></div>
        <h1>Sign in</h1>
        {location.state?.from && <p className="small-note">Your session ended. Sign in again to continue.</p>}
        <label className="field-label" htmlFor="username">Username</label>
        <input id="username" className="form-input" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
        <label className="field-label" htmlFor="password">Password</label>
        <input id="password" className="form-input" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn btn-primary btn-full btn-stacked" disabled={busy || !online}><LogIn size={16} /> {busy ? "Signing in…" : "Sign in"}</button>
        {!online && <p className="small-note">Waiting for the backend server to start…</p>}
      </form>
    </main>
  );
}
