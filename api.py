import hashlib
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src.sop_generator import generate_sop

# -------------------- Paths and settings --------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "originals"
VERSION_DIR = DATA_DIR / "versions"
DB_PATH = DATA_DIR / "safesop.db"
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("safesop")

for folder in (DATA_DIR, UPLOAD_DIR, VERSION_DIR):
    folder.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="SafeSOP AI API",
    description="Document storage and revision workflow API",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now():
    return datetime.now(timezone.utc).isoformat()


def connect_db():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with connect_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS change_requests (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                description TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'full',
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS versions (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                request_id TEXT,
                version_number INTEGER NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id),
                FOREIGN KEY(request_id) REFERENCES change_requests(id),
                UNIQUE(document_id, version_number)
            );
            """
        )


@app.on_event("startup")
def startup():
    init_db()
    logger.info("SafeSOP API started. Database: %s", DB_PATH)


@app.get("/")
def root():
    return {
        "name": "SafeSOP AI API",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/api/health")
def health():
    return {"status": "healthy", "service": "SafeSOP AI"}


@app.get("/api/documents")
def list_documents():
    with connect_db() as connection:
        rows = connection.execute(
            """
            SELECT d.id, d.filename, d.sha256, d.size_bytes, d.created_at,
                   (SELECT COUNT(*) FROM versions v
                    WHERE v.document_id = d.id) AS version_count
            FROM documents d
            ORDER BY d.created_at DESC
            """
        ).fetchall()
    return {"documents": [dict(row) for row in rows]}


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name.strip()

    if not filename:
        raise HTTPException(status_code=400, detail="Please choose a file.")
    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    document_id = str(uuid.uuid4())
    stored_path = UPLOAD_DIR / f"{document_id}.pdf"
    digest = hashlib.sha256()
    size = 0

    try:
        with stored_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
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

        created = now()
        file_hash = digest.hexdigest()

        with connect_db() as connection:
            connection.execute(
                """
                INSERT INTO documents
                    (id, filename, stored_path, sha256, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    filename,
                    str(stored_path),
                    file_hash,
                    size,
                    created,
                ),
            )

        logger.info("Uploaded PDF %s (%s bytes)", filename, size)
        return {
            "id": document_id,
            "filename": filename,
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


@app.get("/api/documents/{document_id}")
def get_document(document_id: str):
    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT id, filename, sha256, size_bytes, created_at
            FROM documents WHERE id = ?
            """,
            (document_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")
    return dict(row)


@app.get("/api/documents/{document_id}/original")
def download_original(document_id: str):
    with connect_db() as connection:
        row = connection.execute(
            "SELECT filename, stored_path FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")
    path = Path(row["stored_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Original PDF file is missing.")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=row["filename"],
    )


@app.post("/api/documents/{document_id}/requests")
def create_change_request(
    document_id: str,
    description: str = Form(...),
    scope: str = Form("full"),
):
    description = description.strip()
    scope = scope.strip().lower()

    if not description:
        raise HTTPException(status_code=400, detail="Describe the process change.")
    if scope not in {"full", "page"}:
        raise HTTPException(
            status_code=400,
            detail="Scope must be 'full' or 'page'.",
        )

    with connect_db() as connection:
        exists = connection.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Document not found.")

        request_id = str(uuid.uuid4())
        created = now()
        connection.execute(
            """
            INSERT INTO change_requests
                (id, document_id, description, scope, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (request_id, document_id, description, scope, created),
        )

    return {
        "id": request_id,
        "document_id": document_id,
        "description": description,
        "scope": scope,
        "created_at": created,
        "status": "saved",
        "message": "Change request saved. Submit it to the generation endpoint to create a draft.",
    }


@app.get("/api/documents/{document_id}/requests")
def list_change_requests(document_id: str):
    with connect_db() as connection:
        exists = connection.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Document not found.")

        rows = connection.execute(
            """
            SELECT * FROM change_requests
            WHERE document_id = ?
            ORDER BY created_at DESC
            """,
            (document_id,),
        ).fetchall()
    return {"requests": [dict(row) for row in rows]}


def extract_document_text(stored_path: str, scope: str, target_page: int | None):
    """Extract text from the immutable uploaded PDF; never modify the source."""
    try:
        with pymupdf.open(stored_path) as pdf:
            if len(pdf) == 0:
                raise HTTPException(status_code=422, detail="The PDF has no pages.")

            if scope == "page":
                if target_page is None:
                    raise HTTPException(
                        status_code=400,
                        detail="For page scope, provide target_page (starting at 1).",
                    )
                if target_page < 1 or target_page > len(pdf):
                    raise HTTPException(
                        status_code=400,
                        detail=f"target_page must be between 1 and {len(pdf)}.",
                    )
                page_text = pdf[target_page - 1].get_text(sort=True).strip()
                if not page_text:
                    raise HTTPException(
                        status_code=422,
                        detail="No selectable text found on that page. OCR is not implemented.",
                    )
                return page_text, target_page

            pages = [
                f"[PAGE {index + 1}]\n{page.get_text(sort=True).strip()}"
                for index, page in enumerate(pdf)
            ]
            text = "\n\n".join(pages).strip()
            if not text:
                raise HTTPException(
                    status_code=422,
                    detail="No selectable text found in this PDF. OCR is not implemented.",
                )
            return text, None
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Could not extract PDF text")
        raise HTTPException(
            status_code=422,
            detail=f"Could not read PDF text: {type(exc).__name__}.",
        ) from exc


@app.post("/api/documents/{document_id}/generate")
def generate_revision(
    document_id: str,
    description: str = Form(...),
    scope: str = Form("full"),
    target_page: int | None = Form(None),
):
    """
    Generate and save an AI draft. This is not safety approval.
    The original PDF remains unchanged.
    """
    description = description.strip()
    scope = scope.strip().lower()

    if not description:
        raise HTTPException(status_code=400, detail="Describe the process change.")
    if scope not in {"full", "page"}:
        raise HTTPException(status_code=400, detail="Scope must be 'full' or 'page'.")

    with connect_db() as connection:
        document = connection.execute(
            "SELECT * FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    original_path = Path(document["stored_path"])
    if not original_path.is_file():
        raise HTTPException(status_code=404, detail="Original PDF file is missing.")

    original_text, resolved_page = extract_document_text(
        str(original_path), scope, target_page
    )

    # Record the request before calling the provider so the requested change is auditable.
    request_id = str(uuid.uuid4())
    created = now()
    with connect_db() as connection:
        connection.execute(
            """
            INSERT INTO change_requests
                (id, document_id, description, scope, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (request_id, document_id, description, scope, created),
        )

    try:
        result = generate_sop(
            original_text=original_text,
            change_request=description,
            output_scope=scope,
            target_page=resolved_page,
        )
    except Exception as exc:
        logger.exception("Gemini SOP generation failed for document %s", document_id)
        # Keep the request record for troubleshooting, but do not create a fake version.
        raise HTTPException(
            status_code=502,
            detail=f"AI generation failed ({type(exc).__name__}). "
                   "Check the backend terminal and Gemini model/quota settings.",
        ) from exc

    generated_text = result["text"]
    version_id = str(uuid.uuid4())
    created_version = now()
    version_file = VERSION_DIR / f"{version_id}.md"

    try:
        with connect_db() as connection:
            next_version = connection.execute(
                """
                SELECT COALESCE(MAX(version_number), 0) + 1 AS next_number
                FROM versions WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()["next_number"]

            version_file.write_text(generated_text, encoding="utf-8")
            connection.execute(
                """
                INSERT INTO versions
                    (id, document_id, request_id, version_number,
                     content, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'draft', ?)
                """,
                (
                    version_id,
                    document_id,
                    request_id,
                    next_version,
                    generated_text,
                    created_version,
                ),
            )
    except Exception as exc:
        if version_file.exists():
            version_file.unlink()
        logger.exception("Could not save generated version")
        raise HTTPException(
            status_code=500,
            detail="Gemini generated a response, but saving the draft failed. "
                   "Check the backend terminal.",
        ) from exc

    return {
        "id": version_id,
        "version_id": version_id,
        "document_id": document_id,
        "request_id": request_id,
        "version_number": next_version,
        "filename": document["filename"],
        "content": generated_text,
        "status": "draft",
        "ai_provider": "Google Gemini",
        "model": result.get("model"),
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "created_at": created_version,
        "safety_evaluation": {
            "status": "not_run",
            "message": (
                "This AI-generated draft has not passed automated safety evaluation "
                "or human approval. Review all warnings and steps before use."
            ),
        },
    }


@app.get("/api/documents/{document_id}/versions")
def list_versions(document_id: str):
    with connect_db() as connection:
        exists = connection.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Document not found.")

        rows = connection.execute(
            """
            SELECT id, document_id, request_id, version_number, status,
                   created_at, length(content) AS characters
            FROM versions
            WHERE document_id = ?
            ORDER BY version_number DESC
            """,
            (document_id,),
        ).fetchall()
    return {"versions": [dict(row) for row in rows]}


@app.get("/api/versions/{version_id}")
def get_version(version_id: str):
    with connect_db() as connection:
        row = connection.execute(
            "SELECT * FROM versions WHERE id = ?",
            (version_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Version not found.")

    result = dict(row)
    result.pop("content", None)
    return result


@app.get("/api/versions/{version_id}/content")
def get_version_content(version_id: str):
    with connect_db() as connection:
        row = connection.execute(
            "SELECT content FROM versions WHERE id = ?",
            (version_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Version not found.")
    return {"version_id": version_id, "content": row["content"]}


@app.get("/api/versions/{version_id}/download")
def download_version(version_id: str):
    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT document_id, version_number, content
            FROM versions WHERE id = ?
            """,
            (version_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Version not found.")

    export_path = VERSION_DIR / f"{version_id}.txt"
    export_path.write_text(row["content"], encoding="utf-8")
    return FileResponse(
        export_path,
        media_type="text/plain",
        filename=f"SafeSOP-v{row['version_number']}.txt",
    )


@app.get("/api/evaluation/status")
def evaluation_status():
    return {
        "status": "not_run",
        "message": (
            "The current generation endpoint does not automatically evaluate "
            "warning preservation, unsupported instructions, or step ordering. "
            "A saved draft is not safety-approved."
        ),
    }
