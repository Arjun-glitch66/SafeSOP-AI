"""Dashboard summary: counts and work queues, computed from the existing tables on each request."""
from fastapi import APIRouter

from app.db import connect_db

router = APIRouter()

# The latest evaluation of each version (the one the review page shows).
LATEST_EVALUATION = """(SELECT e.status FROM evaluations e WHERE e.version_id = v.id
                        ORDER BY e.created_at DESC LIMIT 1)"""


@router.get("/api/overview")
def overview():
    with connect_db() as connection:
        documents = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        by_status = {row["status"]: row["n"] for row in connection.execute(
            "SELECT status, COUNT(*) AS n FROM versions GROUP BY status")}
        by_evaluation = {row["status"] or "not_run": row["n"] for row in connection.execute(
            f"SELECT {LATEST_EVALUATION} AS status, COUNT(*) AS n FROM versions v GROUP BY 1")}
        awaiting_review = [dict(row) for row in connection.execute(
            f"""SELECT v.id, v.version_number, v.status, v.created_at, v.created_by, d.id AS document_id,
                       d.filename, {LATEST_EVALUATION} AS evaluation_status
                FROM versions v JOIN documents d ON d.id = v.document_id
                WHERE v.status IN ('draft', 'needs_revision')
                ORDER BY v.created_at DESC LIMIT 10""")]
        recent_decisions = [dict(row) for row in connection.execute(
            """SELECT r.decision, r.reviewer, r.created_at, v.id AS version_id, v.version_number, d.filename
               FROM review_history r JOIN versions v ON v.id = r.version_id JOIN documents d ON d.id = v.document_id
               ORDER BY r.created_at DESC LIMIT 8""")]
        running_jobs = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'running')").fetchone()[0]
    return {
        "documents": documents,
        "versions": sum(by_status.values()),
        "versions_by_status": by_status,
        "versions_by_evaluation": by_evaluation,
        "awaiting_review": awaiting_review,
        "recent_decisions": recent_decisions,
        "running_jobs": running_jobs,
    }
