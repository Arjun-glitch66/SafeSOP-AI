"""Human review decisions: the only way a version's status changes."""
import hashlib
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException

from app import config
from app.audit import append_audit
from app.pagination import page_params, paginate
from app.auth import check_password, password_hash_of, require_role
from app.db import connect_db, now
from app.schemas import LOCKED_DETAIL, LOCKED_STATUSES, REVIEW_DECISIONS

router = APIRouter()


@router.post("/api/versions/{version_id}/reviews")
def create_review(
    version_id: str,
    decision: str = Form(...),
    feedback: str = Form("", max_length=config.MAX_FEEDBACK_CHARS),
    password: str = Form("", max_length=200),
    user=Depends(require_role("reviewer")),
):
    """Record a human review decision. Only this endpoint changes a version's status.
    The reviewer is the signed-in user, never a typed name. Approval is an electronic
    signature: the reviewer re-enters their password, and the review and audit log record
    the evaluator version, the source PDF's SHA-256 and the approved text's SHA-256."""
    decision = decision.strip().lower()
    reviewer = user["username"]
    feedback = feedback.strip()
    if decision not in REVIEW_DECISIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Decision must be one of: {', '.join(sorted(REVIEW_DECISIONS))}.",
        )

    if decision == "approved" and not check_password(password, password_hash_of(user["id"]) or ""):
        # 403, not 401: a wrong signature must not look like an expired session.
        raise HTTPException(status_code=403, detail="Re-enter your password to sign this approval.")

    review_id = str(uuid.uuid4())
    created = now()
    with connect_db() as connection:
        connection.lock_writes()  # status check, update and audit event in one transaction
        version = connection.execute(
            """SELECT v.status, v.created_by, v.content, d.sha256 AS source_sha256
               FROM versions v JOIN documents d ON d.id = v.document_id WHERE v.id = ?""", (version_id,)
        ).fetchone()
        if not version:
            raise HTTPException(status_code=404, detail="Version not found.")
        if decision == "approved" and version["created_by"] == reviewer:
            # Separation of duties: whoever generated a draft cannot also approve it.
            raise HTTPException(status_code=403, detail="You generated this version, so another reviewer must approve it.")
        if version["status"] in LOCKED_STATUSES:
            raise HTTPException(status_code=409, detail=LOCKED_DETAIL)

        latest = connection.execute(
            "SELECT status, evaluator_version FROM evaluations WHERE version_id = ? ORDER BY created_at DESC LIMIT 1",
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
        signed = {
            "evaluator_version": latest["evaluator_version"] if latest else None,
            "evaluation_status": latest["status"] if latest else None,
            "source_sha256": version["source_sha256"],
            "content_sha256": hashlib.sha256(version["content"].encode("utf-8")).hexdigest(),
        }
        connection.execute(
            """
            INSERT INTO review_history
                (id, version_id, decision, reviewer, feedback, created_at,
                 evaluator_version, evaluation_status, source_sha256, content_sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (review_id, version_id, decision, reviewer, feedback, created, *signed.values()),
        )
        append_audit(connection, reviewer, f"version_{decision}", "version", version_id,
                     {"review_id": review_id, "feedback": feedback,
                      "password_reentered": decision == "approved", **signed})

    return {
        "id": review_id,
        "version_id": version_id,
        "decision": decision,
        "reviewer": reviewer,
        "feedback": feedback,
        "created_at": created,
        **signed,
    }


@router.get("/api/versions/{version_id}/reviews")
def list_reviews(version_id: str, page=Depends(page_params)):
    with connect_db() as connection:
        return paginate(connection, """
            SELECT * FROM review_history
            WHERE version_id = ?
            ORDER BY created_at DESC, id
            """, (version_id,), page, "reviews")
