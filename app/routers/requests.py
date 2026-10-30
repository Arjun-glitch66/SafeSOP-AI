"""Change requests, saved before or during generation."""
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException

from app import config
from app.auth import require_role
from app.db import connect_db, now
from app.pagination import page_params, paginate

router = APIRouter()


@router.post("/api/documents/{document_id}/requests")
def create_change_request(
    document_id: str,
    description: str = Form(..., max_length=config.MAX_DESCRIPTION_CHARS),
    scope: str = Form("full"),
    target_page: int | None = Form(None),
    target_section: str | None = Form(None, max_length=20),
    user=Depends(require_role("author")),
):
    description = description.strip()
    scope = scope.strip().lower()
    target_section = (target_section or "").strip().upper() or None

    if not description:
        raise HTTPException(status_code=400, detail="Describe the process change.")
    if scope not in {"full", "page", "section", "step"}:
        raise HTTPException(
            status_code=400,
            detail="Scope must be 'full', 'page', 'section' or 'step'.",
        )
    if scope != "page":
        target_page = None
    elif target_page is None or target_page < 1:
        raise HTTPException(status_code=400, detail="For page scope, provide target_page (starting at 1).")
    if scope in ("section", "step"):
        if not target_section:
            raise HTTPException(status_code=400, detail=f"For {scope} scope, choose target_section.")
    else:
        target_section = None

    with connect_db() as connection:
        document = connection.execute(
            "SELECT page_count FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found.")
        if target_page and document["page_count"] and target_page > document["page_count"]:
            raise HTTPException(
                status_code=400,
                detail=f"target_page must be between 1 and {document['page_count']}.",
            )

        request_id = str(uuid.uuid4())
        created = now()
        connection.execute(
            """
            INSERT INTO change_requests
                (id, document_id, description, scope, target_page, target_section, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (request_id, document_id, description, scope, target_page, target_section, created),
        )

    return {
        "id": request_id,
        "document_id": document_id,
        "description": description,
        "scope": scope,
        "target_page": target_page,
        "target_section": target_section,
        "created_at": created,
        "status": "saved",
        "message": "Change request saved. Submit it to the generation endpoint to create a draft.",
    }


@router.get("/api/documents/{document_id}/requests")
def list_change_requests(document_id: str, page=Depends(page_params)):
    with connect_db() as connection:
        exists = connection.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Document not found.")

        return paginate(connection, """
            SELECT * FROM change_requests
            WHERE document_id = ?
            ORDER BY created_at DESC, id
            """, (document_id,), page, "requests")
