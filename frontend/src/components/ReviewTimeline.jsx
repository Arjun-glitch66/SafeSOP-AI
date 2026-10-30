import { statusLabel } from "./labels.js";

// Recorded human decisions, newest first. Approval is never inferred from an automated result.
export default function ReviewTimeline({ reviews, status }) {
  return (
    <section className="panel" aria-labelledby="reviews-heading">
      <div className="panel-heading"><div><h2 id="reviews-heading">Qualified human review: {statusLabel(status).toLowerCase()}</h2><p>Approval is never inferred from an automated result.</p></div></div>
      {reviews.error && <p className="form-error" role="alert">Could not load reviews: {reviews.error.message}</p>}
      {reviews.data?.length === 0 && <p className="small-note">No review decisions yet.</p>}
      <ol className="review-list">
        {reviews.data?.map((review) => (
          <li key={review.id}>
            <strong>{review.decision.replace("_", " ")}</strong> by {review.reviewer} · {new Date(review.created_at).toLocaleString()}
            {review.feedback && <p>{review.feedback}</p>}
            {review.decision === "approved" && review.content_sha256 && <small>Signed with password re-entry · checks {review.evaluation_status || "not run"} ({review.evaluator_version || "no evaluation"}) · source PDF {review.source_sha256?.slice(0, 12)}… · draft {review.content_sha256.slice(0, 12)}…</small>}
          </li>
        ))}
      </ol>
    </section>
  );
}
