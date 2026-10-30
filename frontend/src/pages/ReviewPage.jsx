import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { CheckCircle2, FileText, Lock, RefreshCw, X } from "lucide-react";
import { createReview, getReviews, getVersion } from "../api.js";
import ReviewTimeline from "../components/ReviewTimeline.jsx";
import SignOffDialog from "../components/SignOffDialog.jsx";
import VersionEvidence from "../components/VersionEvidence.jsx";
import { EmptyState } from "../components/ui.jsx";
import { evaluationLabel } from "../components/labels.js";
import { useAuth, useNotice, useResource, useTitle } from "../state.jsx";

// Evidence first (checks, comparison, earlier decisions); the decision comes last.
export default function ReviewPage() {
  const { versionId } = useParams();
  const version = useResource(() => getVersion(versionId), [versionId]);
  const reviews = useResource(() => getReviews(versionId), [versionId]);
  const v = version.data;
  useTitle(v ? `Review version ${v.version_number} · ${v.filename}` : "Review");
  const { user, can } = useAuth();
  const { show } = useNotice();
  const navigate = useNavigate();
  const [feedback, setFeedback] = useState("");
  const [signing, setSigning] = useState(false);
  const [busy, setBusy] = useState(false);

  if (version.error) return <EmptyState icon={FileText} title="Version not available" text={version.error.message} action={<Link className="btn btn-primary" to="/documents">Back to documents</Link>} />;
  if (!v) return <p className="small-note">Loading version…</p>;

  const ownDraft = v.created_by && v.created_by === user.username;

  async function decide(decision) {
    setBusy(true);
    try {
      await createReview(v.id, { decision, feedback });
      show(`Review saved: ${decision.replace("_", " ")}.`);
      navigate(`/versions/${v.id}`);
    } catch (error) {
      show(`Could not save review: ${error.message}`, "error");
    } finally {
      setBusy(false);
    }
  }

  async function sign({ justification, password }) {
    await createReview(v.id, { decision: "approved", feedback: justification, password });  // errors shown in the dialog
    setSigning(false);
    show(`Version ${v.version_number} approved and signed.`);
    navigate(`/versions/${v.id}`);
  }

  return (
    <>
      <div className="page-intro">
        <div>
          <p className="title-block-kicker"><Link to={`/versions/${v.id}`}>{v.filename} · version {v.version_number}</Link></p>
          <h1>Review version {v.version_number}</h1>
          <p>Read the automated findings and the comparison first. Automated checks: <strong>{evaluationLabel[v.evaluation_status] || "not run"}</strong>; they never approve a draft.</p>
        </div>
      </div>

      <VersionEvidence versionId={v.id} onEvaluated={version.reload} />
      <ReviewTimeline reviews={reviews} status={v.status} />

      <section className="panel" aria-labelledby="decision-heading">
        <div className="panel-heading"><div><h2 id="decision-heading">Your decision</h2><p>Signed in as {user.username}. Your name is recorded with the decision.</p></div></div>
        {v.status === "approved" ? <p className="small-note"><Lock size={14} /> This version is approved and locked. Regenerate from the original to make further changes.</p>
          : !can("reviewer") ? <p className="small-note">Only reviewers can record a decision.</p>
          : <>
            <label className="field-label" htmlFor="review-feedback">Review comments</label>
            <textarea id="review-feedback" className="form-textarea" rows={3} maxLength={2000} value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="What was checked, and what must change?" />
            {ownDraft && <p className="small-note">You generated this version, so another reviewer must approve it. You can still ask for a revision or reject it.</p>}
            <div className="action-row">
              <button className="btn btn-primary" disabled={busy || ownDraft} onClick={() => setSigning(true)}><CheckCircle2 size={16} /> Approve…</button>
              <button className="btn btn-secondary" disabled={busy} onClick={() => decide("needs_revision")}><RefreshCw size={16} /> Needs revision</button>
              <button className="btn btn-secondary" disabled={busy} onClick={() => decide("rejected")}><X size={16} /> Reject</button>
            </div>
            <SignOffDialog open={signing} version={v} initialJustification={feedback} onSign={sign} onClose={() => setSigning(false)} />
          </>}
      </section>
    </>
  );
}
