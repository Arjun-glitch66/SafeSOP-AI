import { Link } from "react-router";
import { ClipboardCheck, FileClock, Files, FlaskConical, Inbox, Loader } from "lucide-react";
import { getOverview } from "../api.js";
import { Badge, EmptyState, MetricCard } from "../components/ui.jsx";
import { evaluationLabel, evaluationTone, statusLabel, statusTone } from "../components/labels.js";
import { useAuth, useBackend, useResource, useTitle } from "../state.jsx";

// Live counts from GET /api/overview: nothing on this page is sample data.
export default function DashboardPage() {
  useTitle("Dashboard");
  const { online } = useBackend();
  const { user, can } = useAuth();
  const overview = useResource(getOverview, [online]);
  const data = overview.data;
  const byStatus = data?.versions_by_status || {};
  const byCheck = data?.versions_by_evaluation || {};
  const awaiting = (byStatus.draft || 0) + (byStatus.needs_revision || 0);

  return (
    <>
      <div className="page-intro">
        <div><h1>Dashboard</h1><p>Signed in as {user.username} ({user.role}). {can("reviewer") ? "Drafts waiting for a decision are listed below." : "Upload an SOP and describe a change to create a draft."}</p></div>
        {can("author") && <Link className="btn btn-primary" to="/documents"><Files size={16} /> Documents</Link>}
      </div>

      {overview.error && <p className="form-error" role="alert">Could not load the overview: {overview.error.message}</p>}
      {data && <div className="metrics-grid">
        <MetricCard label="Source documents" value={data.documents} note="Original PDFs, never modified" icon={Files} tone="blue" />
        <MetricCard label="Generated versions" value={data.versions} note={`${byStatus.approved || 0} approved · ${byStatus.rejected || 0} rejected`} icon={FileClock} tone="purple" />
        <MetricCard label="Awaiting review" value={awaiting} note={`${byStatus.needs_revision || 0} marked needs revision`} icon={ClipboardCheck} tone="amber" />
        <MetricCard label="Automated checks" value={`${byCheck.fail || 0} fail`} note={`${byCheck.needs_review || 0} needs review · ${byCheck.pass_automated || 0} no rule fired · ${byCheck.not_run || 0} not run`} icon={FlaskConical} tone="red" />
      </div>}
      {data?.running_jobs > 0 && <p className="small-note"><Loader size={14} /> {data.running_jobs} generation job(s) running.</p>}

      <section className="panel" aria-labelledby="queue-heading">
        <div className="panel-heading"><div><h2 id="queue-heading">Review queue</h2><p>Latest drafts that are not approved or rejected yet, newest first.</p></div></div>
        {data?.awaiting_review.length === 0 && <EmptyState icon={Inbox} title="Nothing waiting for review" text="New drafts appear here as soon as they are generated." />}
        {data?.awaiting_review.length > 0 && <div className="table-wrap"><table className="data-table">
          <thead><tr><th>Document</th><th>Version</th><th>Generated</th><th>Automated check</th><th>Status</th><th><span className="sr-only">Action</span></th></tr></thead>
          <tbody>{data.awaiting_review.map((item) => (
            <tr key={item.id}>
              <td><Link to={`/documents/${item.document_id}`}>{item.filename}</Link></td>
              <td><Link to={`/versions/${item.id}`}>Version {item.version_number}</Link></td>
              <td>{new Date(item.created_at).toLocaleString()}{item.created_by ? ` · ${item.created_by}` : ""}</td>
              <td><Badge tone={evaluationTone[item.evaluation_status] || "gray"}>{evaluationLabel[item.evaluation_status] || "Not run"}</Badge></td>
              <td><Badge tone={statusTone(item.status)} dot>{statusLabel(item.status)}</Badge></td>
              <td>{can("reviewer") && <Link className="btn btn-secondary" to={`/versions/${item.id}/review`}>Review</Link>}</td>
            </tr>
          ))}</tbody>
        </table></div>}
      </section>

      <section className="panel" aria-labelledby="decisions-heading">
        <div className="panel-heading"><div><h2 id="decisions-heading">Recent review decisions</h2><p>Every decision is also in the hash-chained audit log.</p></div></div>
        {data?.recent_decisions.length === 0 && <p className="small-note">No review decisions yet.</p>}
        {data?.recent_decisions.map((item) => (
          <div className="document-row" key={`${item.version_id}-${item.created_at}`}>
            <div className="row-main"><strong><Link to={`/versions/${item.version_id}`}>{item.filename} · version {item.version_number}</Link></strong><span>{item.reviewer} · {new Date(item.created_at).toLocaleString()}</span></div>
            <Badge tone={statusTone(item.decision)} dot>{statusLabel(item.decision)}</Badge>
          </div>
        ))}
      </section>
    </>
  );
}
