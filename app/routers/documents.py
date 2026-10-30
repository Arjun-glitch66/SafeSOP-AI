"""Uploading and reading the original PDFs."""
import hashlib
import logging
import uuid
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import config
from app.audit import append_audit
from app.auth import require_role
from app.db import connect_db, now
from app.pagination import page_params, paginate
from app.storage import resolve, to_stored_path
from src.checklists import available_types

logger = logging.getLogger("safesop")
router = APIRouter()


@router.get("/api/documents")
def list_documents(page=Depends(page_params)):
    with connect_db() as connection:
        return paginate(connection, """
            SELECT d.id, d.filename, d.sha256, d.size_bytes, d.created_at, d.document_type,
                   (SELECT COUNT(*) FROM versions v
                    WHERE v.document_id = d.id) AS version_count
            FROM documents d
            ORDER BY d.created_at DESC, d.id
            """, (), page, "documents")


@router.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...), document_type: str = Form(""),
                          user=Depends(require_role("author"))):
    filename = Path(file.filename or "").name.strip()
    doc_type = document_type.strip() or None
    if doc_type and doc_type not in {pack["id"] for pack in available_types()}:
        raise HTTPException(status_code=400, detail=f"Unknown document type '{doc_type}'. See GET /api/checklists.")

    if not filename:
        raise HTTPException(status_code=400, detail="Please choose a file.")
    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    document_id = str(uuid.uuid4())
    stored_path = config.UPLOAD_DIR / f"{document_id}.pdf"
    digest = hashlib.sha256()
    size = 0

    try:
        with stored_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > config.MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="PDF exceeds the 20 MB upload limit.",
                    )
                digest.update(chunk)
                destination.write(chunk)

        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")

        with stored_path.open("rb") as source:
            if source.read(5) != b"%PDF-":
                raise HTTPException(
                    status_code=400,
                    detail="The file does not appear to be a valid PDF.",
                )

        try:
            with pymupdf.open(stored_path) as pdf:
                page_count = len(pdf)
        except Exception:
            raise HTTPException(status_code=400, detail="The PDF could not be opened.") from None

        created = now()
        file_hash = digest.hexdigest()

        with connect_db() as connection:
            connection.lock_writes()  # audit chain head is read in this transaction
            connection.execute(
                """
                INSERT INTO documents
                    (id, filename, stored_path, sha256, size_bytes, created_at, page_count, document_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    filename,
                    to_stored_path(stored_path),
                    file_hash,
                    size,
                    created,
                    page_count,
                    doc_type,
                ),
            )
            append_audit(connection, user["username"], "document_uploaded", "document", document_id,
                         {"filename": filename, "sha256": file_hash, "size_bytes": size, "page_count": page_count,
                          "document_type": doc_type})

        logger.info("Uploaded PDF %s (%s bytes)", filename, size)
        return {
            "id": document_id,
            "filename": filename,
            "document_type": doc_type,
            "sha256": file_hash,
            "size_bytes": size,
            "created_at": created,
            "message": "Original PDF stored successfully.",
        }

    except HTTPException:
        if stored_path.exists():
            stored_path.unlink()
        raise
    except Exception as exc:
        if stored_path.exists():
            stored_path.unlink()
        logger.exception("PDF upload failed")
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed on the server: {type(exc).__name__}. "
                   "Check the backend terminal for the full traceback.",
        ) from exc
    finally:
        await file.close()


@router.get("/api/documents/{document_id}")
def get_document(document_id: str):
    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT id, filename, stored_path, sha256, size_bytes, created_at, page_count, document_type
            FROM documents WHERE id = ?
            """,
            (document_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")

    result = dict(row)
    stored_path = result.pop("stored_path")
    if result["page_count"] is None:
        # Documents uploaded before page_count existed: count once, then store it.
        try:
            with pymupdf.open(resolve(stored_path)) as pdf:
                result["page_count"] = len(pdf)
            with connect_db() as connection:
                connection.execute("UPDATE documents SET page_count = ? WHERE id = ?",
                                   (result["page_count"], document_id))
        except Exception:
            logger.exception("Could not read page count for %s", document_id)
    return result


@router.get("/api/documents/{document_id}/original")
def download_original(document_id: str):
    with connect_db() as connection:
        row = connection.execute(
            "SELECT filename, stored_path FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")
    path = resolve(row["stored_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Original PDF file is missing.")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=row["filename"],
    )


@router.get("/api/checklists")
def list_checklists():
    """SOP types with a required-element checklist; pass one as document_type at upload."""
    return {"checklists": available_types()}
