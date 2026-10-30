import { useEffect, useRef, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { evaluationLabel } from "./labels.js";

// Approval as an electronic signature: the reviewer confirms what they are signing, gives a
// justification when the automated checks did not pass, and re-enters their password.
// The server enforces all three; this dialog only collects them. Uses the native <dialog>
// for focus trapping and Escape-to-close.
export default function SignOffDialog({ open, version, initialJustification, onSign, onClose }) {
  const dialog = useRef(null);
  const [justification, setJustification] = useState(initialJustification);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const checksPassed = version.evaluation_status === "pass_automated";

  useEffect(() => {
    if (open && !dialog.current.open) {
      setJustification(initialJustification);
      setPassword("");
      setError("");
      dialog.current.showModal();
    } else if (!open && dialog.current.open) {
      dialog.current.close();
    }
  }, [open, initialJustification]);

  async function submit(event) {
    event.preventDefault();
    if (!checksPassed && !justification.trim()) {
      setError("The automated checks did not pass. Explain why you are approving anyway.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSign({ justification: justification.trim(), password });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog ref={dialog} className="signoff-dialog" aria-labelledby="signoff-title" onClose={onClose}>
      <form onSubmit={submit}>
        <h2 id="signoff-title"><ShieldCheck size={20} /> Sign off version {version.version_number}</h2>
        <dl className="signoff-facts">
          <div><dt>Document</dt><dd>{version.filename}</dd></div>
          <div><dt>Automated checks</dt><dd>{evaluationLabel[version.evaluation_status] || "Not run"}</dd></div>
        </dl>
        <p className="small-note">You are approving this draft as the qualified reviewer. Your name, the time, the evaluator version and fingerprints of the original PDF and this exact draft are recorded in the audit log.</p>
        <label className="field-label" htmlFor="signoff-justification">Justification{checksPassed ? " (optional)" : <span className="required"> * required: checks did not pass</span>}</label>
        <textarea id="signoff-justification" className="form-textarea" rows={4} maxLength={2000} value={justification} onChange={(event) => setJustification(event.target.value)} placeholder="What did you check, and why is this draft acceptable?" />
        <label className="field-label" htmlFor="signoff-password">Your password</label>
        <input id="signoff-password" className="form-input" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="action-row">
          <button className="btn btn-primary" disabled={busy}>{busy ? "Signing…" : "Sign and approve"}</button>
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </dialog>
  );
}
