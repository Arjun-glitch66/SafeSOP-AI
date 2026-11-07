import { useState } from "react";
import { KeyRound } from "lucide-react";
import { changePassword } from "../api.js";
import { useAuth, useNotice, useTitle } from "../state.jsx";

const MIN_PASSWORD = 10;

export default function AccountPage() {
  useTitle("Account");
  const { user } = useAuth();
  const { show } = useNotice();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (next.length < MIN_PASSWORD) { setError(`The new password needs at least ${MIN_PASSWORD} characters.`); return; }
    if (next !== repeat) { setError("The two new passwords do not match."); return; }
    setBusy(true);
    try {
      await changePassword(current, next);
      setCurrent(""); setNext(""); setRepeat("");
      show("Password changed. Sessions on other devices have ended.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-intro"><div><h1>Account</h1><p>{user.username} · {user.role}</p></div></div>
      <section className="panel" aria-labelledby="password-heading">
        <div className="panel-heading"><div><h2 id="password-heading">Change password</h2><p>Your password is also your approval signature. Changing it signs you out everywhere else.</p></div></div>
        <form onSubmit={submit}>
          <label className="field-label" htmlFor="current-password">Current password</label>
          <input id="current-password" className="form-input" type="password" autoComplete="current-password" required value={current} onChange={(event) => setCurrent(event.target.value)} />
          <label className="field-label" htmlFor="new-password">New password (at least {MIN_PASSWORD} characters)</label>
          <input id="new-password" className="form-input" type="password" autoComplete="new-password" required value={next} onChange={(event) => setNext(event.target.value)} />
          <label className="field-label" htmlFor="repeat-password">Repeat the new password</label>
          <input id="repeat-password" className="form-input" type="password" autoComplete="new-password" required value={repeat} onChange={(event) => setRepeat(event.target.value)} />
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="action-row"><button className="btn btn-primary" disabled={busy}><KeyRound size={16} /> {busy ? "Changing…" : "Change password"}</button></div>
        </form>
      </section>
    </>
  );
}
