"""Human review decisions: the only way a version's status changes."""
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException

from app import config
from app.auth import require_role
from app.db import connect_db, now
from app.schemas import LOCKED_DETAIL, LOCKED_STATUSES, REVIEW_DECISIONS

router = APIRouter()


@router.post("/api/versions/{version_id}/reviews")
def create_review(
    version_id: str,
    decision: str = Form(...),
    feedback: str = Form("", max_length=config.MAX_FEEDBACK_CHARS),
    user=Depends(require_role("reviewer")),
):
    """Record a human review decision. Only this endpoint changes a version's status.
    The reviewer is the signed-in user, never a typed name."""
    decision = decision.strip().lower()
    reviewer = user["username"]
    feedback = feedback.strip()
    if decision not in REVIEW_DECISIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Decision must be one of: {', '.join(sorted(REVIEW_DECISIONS))}.",
        )

    review_id = str(uuid.uuid4())
    created = now()
    with connect_db() as connection:
        version = connection.execute(
            "SELECT status, created_by FROM versions WHERE id = ?", (version_id,)
        ).fetchone()
        if not version:
            raise HTTPException(status_code=404, detail="Version not found.")
        if decision == "approved" and version["created_by"] == reviewer:
            # Separation of duties: whoever generated a draft cannot also approve it.
            raise HTTPException(status_code=403, detail="You generated this version, so another reviewer must approve it.")
        if version["status"] in LOCKED_STATUSES:
            raise HTTPException(status_code=409, detail=LOCKED_DETAIL)

        latest = connection.execute(
            "SELECT status FROM evaluations WHERE version_id = ? ORDER BY created_at DESC LIMIT 1",
            (version_id,),
        ).fetchone()
        if decision == "approved" and (latest is None or latest["status"] != "pass_automated") and not feedback:
            # Enforced here, not only in the UI: approving against failed or missing
            # automated checks needs a recorded justification.
            raise HTTPException(
                status_code=400,
                detail="Automated checks did not pass (or were not run). Approving requires a "
                       "written justification in the review comments.",
            )

        # Conditional update: if a concurrent review locked the version since the read
        # above, nothing changes and this review is refused (the `with` block rolls back).
        changed = connection.execute(
            f"UPDATE versions SET status = ? WHERE id = ? "
            f"AND status NOT IN ({', '.join('?' * len(LOCKED_STATUSES))})",
            (decision, version_id, *LOCKED_STATUSES),
        ).rowcount
        if not changed:
            raise HTTPException(status_code=409, detail=LOCKED_DETAIL)
        connection.execute(
            """
            INSERT INTO review_history
                (id, version_id, decision, reviewer, feedback, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (review_id, version_id, decision, reviewer, feedback, created),
        )

    return {
        "id": review_id,
        "version_id": version_id,
        "decision": decision,
        "reviewer": reviewer,
        "feedback": feedback,
        "created_at": created,
    }


@router.get("/api/versions/{version_id}/reviews")
def list_reviews(version_id: str):
    with connect_db() as connection:
        rows = connection.execute(
            """
            SELECT * FROM review_history
            WHERE version_id = ?
            ORDER BY created_at DESC
            """,
            (version_id,),
        ).fetchall()
    return {"reviews": [dict(row) for row in rows]}
