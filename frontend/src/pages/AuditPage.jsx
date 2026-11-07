import { useState } from "react";
import { Link } from "react-router";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { getAuditEvents, verifyAuditChain } from "../api.js";
import { Badge } from "../components/ui.jsx";
import { useNotice, useResource, useTitle } from "../state.jsx";

const PAGE = 50;

function target(event) {
  if (event.entity === "version") return <Link to={`/versions/${event.entity_id}`}>version</Link>;
  if (event.entity === "document") return <Link to={`/documents/${event.entity_id}`}>document</Link>;
  return event.payload?.username ? `user ${event.payload.username}` : event.entity;
}

// Admin only. The log is append-only and hash-chained; "Verify" recomputes every hash on the server.
export default function AuditPage() {
  useTitle("Audit log");
  const { show } = useNotice();
  const [offset, setOffset] = useState(0);
  const events = useResource(() => getAuditEvents(PAGE, offset), [offset]);
  const [verification, setVerification] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const total = events.data?.total ?? 0;

  async function verify() {
    setVerifying(true);
    try {
      setVerification(await verifyAuditChain());
    } catch (error) {
      show(`Verification failed to run: ${error.message}`, "error");
    } finally {
      setVerifying(false);
    }
  }

  return (
    <>
      <div className="page-intro">
        <div><h1>Audit log</h1><p>Uploads, generations, review decisions and account changes, newest first. Each event's hash covers the previous one, so a changed, removed or reordered event breaks the chain.</p></div>
        <button className="btn btn-primary" disabled={verifying} onClick={verify}><ShieldCheck size={16} /> {verifying ? "Verifying…" : "Verify chain"}</button>
      </div>

      {verification && (verification.ok
        ? <div className="notice-banner" role="status"><ShieldCheck size={20} /><div><strong>Chain intact</strong><p>All {verification.events} events check out. Head hash: <code>{verification.head}</code></p></div></div>
        : <div className="notice-banner" role="alert"><ShieldAlert size={20} /><div><strong>Chain broken at event #{verification.broken_at}</strong><p>{verification.reason}. Event id {verification.event_id}.</p></div></div>)}

      <section className="panel" aria-labelledby="events-heading">
        <div className="panel-heading"><div><h2 id="events-heading">Events</h2><p>{total} in total</p></div></div>
        {events.error && <p className="form-error" role="alert">Could not load the audit log: {events.error.message}</p>}
        {events.data && <div className="table-wrap"><table className="data-table text-table">
          <thead><tr><th>#</th><th>Time (local)</th><th>User</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
          <tbody>{events.data.events.map((event) => (
            <tr key={event.id}>
              <td>{event.seq}</td>
              <td>{new Date(event.ts).toLocaleString()}</td>
              <td>{event.user}</td>
              <td><Badge tone={event.action.startsWith("version_approved") ? "green" : event.action.startsWith("version_rejected") ? "red" : "gray"}>{event.action.replaceAll("_", " ")}</Badge></td>
              <td>{target(event)}</td>
              <td className="small-note wrap">{Object.entries(event.payload || {}).filter(([key]) => !key.endsWith("sha256") && key !== "review_id").map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`).join(" · ").slice(0, 220)}</td>
            </tr>
          ))}</tbody>
        </table></div>}
        <div className="action-row">
          <button className="btn btn-secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Newer</button>
          <button className="btn btn-secondary" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Older</button>
        </div>
      </section>
    </>
  );
}
