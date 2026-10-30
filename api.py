import difflib
import hashlib
import html
import io
import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from src.safety_evaluator import (
    EVALUATOR_VERSION,
    evaluate_revision,
    extract_draft_section,
    extract_warnings,
    text_lines,
)
from src.sop_generator import generate_sop

# -------------------- Paths and settings --------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "originals"
VERSION_DIR = DATA_DIR / "versions"
DB_PATH = DATA_DIR / "safesop.db"
BACKUP_DIR = DATA_DIR / "backups"
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
# Checked before the (billed) Gemini call. Text limits are enforced by FastAPI as 422s.
MAX_PDF_PAGES = 50
MAX_SOURCE_CHARS = 60_000
MAX_DESCRIPTION_CHARS = 2000
MAX_FEEDBACK_CHARS = 2000
MAX_REVIEWER_CHARS = 100

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("safesop")

for folder in (DATA_DIR, UPLOAD_DIR, VERSION_DIR):
    folder.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(_app):
    init_db()
    logger.info("SafeSOP API started. Database: %s", DB_PATH)
    yield


app = FastAPI(
    title="SafeSOP AI API",
    description="Document storage and revision workflow API",
    version="1.2.0",
    lifespan=lifespan,
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


# Columns added after the first release. Added with ALTER TABLE so existing rows are kept.
VERSION_COLUMNS = {
    "source_document_id": "TEXT REFERENCES documents(id)",
    "parent_version_id": "TEXT REFERENCES versions(id)",
    "target_page": "INTEGER",
    "model": "TEXT",
    "prompt_version": "TEXT",
    "input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
    "temperature": "REAL",
    "structured_output": "INTEGER",
}

DOCUMENT_COLUMNS = {
    "page_count": "INTEGER",
}

# Version states: draft -> needs_revision | approved | rejected. Approved versions are
# locked; any further review is refused with 409. Changes go into a new version.
REVIEW_DECISIONS = {"approved", "rejected", "needs_revision"}
LOCKED_STATUSES = ("approved",)
LOCKED_DETAIL = "This version is approved and locked. Generate a new version to make changes."


def init_db():
    with connect_db() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(documents)")}
        if columns and "stored_path" not in columns:
            # The legacy Streamlit schema (integer IDs) owns this file. Refuse rather than mix schemas.
            raise RuntimeError(
                f"{DB_PATH} uses the legacy Streamlit schema. Move it aside "
                "(it is not deleted automatically) and restart the API."
            )

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

            CREATE TABLE IF NOT EXISTS evaluations (
                id TEXT PRIMARY KEY,
                version_id TEXT NOT NULL,
                status TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                evaluator_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(version_id) REFERENCES versions(id)
            );

            CREATE TABLE IF NOT EXISTS review_history (
                id TEXT PRIMARY KEY,
                version_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                reviewer TEXT,
                feedback TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(version_id) REFERENCES versions(id)
            );
            """
        )

        missing = []
        for table, wanted in (("documents", DOCUMENT_COLUMNS), ("versions", VERSION_COLUMNS)):
            existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
            missing += [(table, name, sql) for name, sql in wanted.items() if name not in existing]

        has_rows = connection.execute(
            "SELECT (SELECT COUNT(*) FROM versions) + (SELECT COUNT(*) FROM documents)"
        ).fetchone()[0] > 0
        if missing and has_rows:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup_path = BACKUP_DIR / f"safesop-{datetime.now():%Y%m%d-%H%M%S}.db"
            backup = sqlite3.connect(backup_path)
            try:
                connection.backup(backup)
            finally:
                backup.close()
            logger.info("Backed up database to %s before migration", backup_path)

        # Table and column names come from the constants above, never from user input.
        for table, name, sql in missing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql}")
        if missing:
            logger.info("Added columns: %s", ", ".join(f"{t}.{n}" for t, n, _ in missing))

        # Every pre-lineage version was generated from its own document's original PDF.
        # Runs on every start so an interrupted migration still gets backfilled.
        connection.execute(
            "UPDATE versions SET source_document_id = document_id WHERE source_document_id IS NULL"
        )


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

        try:
            with pymupdf.open(stored_path) as pdf:
                page_count = len(pdf)
        except Exception:
            raise HTTPException(status_code=400, detail="The PDF could not be opened.") from None

        created = now()
        file_hash = digest.hexdigest()

        with connect_db() as connection:
            connection.execute(
                """
                INSERT INTO documents
                    (id, filename, stored_path, sha256, size_bytes, created_at, page_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    filename,
                    str(stored_path),
                    file_hash,
                    size,
                    created,
                    page_count,
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
            SELECT id, filename, stored_path, sha256, size_bytes, created_at, page_count
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
            with pymupdf.open(stored_path) as pdf:
                result["page_count"] = len(pdf)
            with connect_db() as connection:
                connection.execute("UPDATE documents SET page_count = ? WHERE id = ?",
                                   (result["page_count"], document_id))
        except Exception:
            logger.exception("Could not read page count for %s", document_id)
    return result


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
    description: str = Form(..., max_length=MAX_DESCRIPTION_CHARS),
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


def extract_document_text(stored_path: str, scope: str, target_page: int | None,
                          max_pages: int | None = None):
    """Extract text from the immutable uploaded PDF; never modify the source."""
    try:
        with pymupdf.open(stored_path) as pdf:
            if len(pdf) == 0:
                raise HTTPException(status_code=422, detail="The PDF has no pages.")
            if scope == "full" and max_pages and len(pdf) > max_pages:
                raise HTTPException(
                    status_code=413,
                    detail=f"The PDF has {len(pdf)} pages; full-document revision supports up to "
                           f"{max_pages}. Revise one page at a time instead.",
                )

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
    description: str = Form(..., max_length=MAX_DESCRIPTION_CHARS),
    scope: str = Form("full"),
    target_page: int | None = Form(None),
    parent_version_id: str | None = Form(None),
):
    """
    Generate and save an AI draft. This is not safety approval.
    The original PDF remains unchanged and is always the generation source;
    parent_version_id only records which earlier draft this one revises.
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

        parent = None
        if parent_version_id:
            parent = connection.execute(
                "SELECT id FROM versions WHERE id = ? AND document_id = ?",
                (parent_version_id, document_id),
            ).fetchone()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    if parent_version_id and not parent:
        raise HTTPException(
            status_code=400,
            detail="parent_version_id must be a version of this document.",
        )

    original_path = Path(document["stored_path"])
    if not original_path.is_file():
        raise HTTPException(status_code=404, detail="Original PDF file is missing.")

    original_text, resolved_page = extract_document_text(
        str(original_path), scope, target_page, max_pages=MAX_PDF_PAGES
    )
    if len(original_text) > MAX_SOURCE_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"The source text is {len(original_text):,} characters; the limit is "
                   f"{MAX_SOURCE_CHARS:,}. Revise one page at a time instead.",
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
        # RuntimeErrors come from sop_generator's own config checks and contain no secrets.
        reason = str(exc) if isinstance(exc, RuntimeError) else (
            f"{type(exc).__name__}. Check the backend terminal and Gemini model/quota settings."
        )
        raise HTTPException(status_code=502, detail=f"AI generation failed: {reason}") from exc

    generated_text = result["text"]
    version_id = str(uuid.uuid4())
    created_version = now()
    version_file = VERSION_DIR / f"{version_id}.md"

    try:
        version_file.write_text(generated_text, encoding="utf-8")
        next_version = insert_numbered_version(
            document_id,
            (
                version_id,
                document_id,
                request_id,
                generated_text,
                created_version,
                document_id,
                parent_version_id or None,
                resolved_page,
                result.get("model"),
                result.get("prompt_version"),
                result.get("input_tokens"),
                result.get("output_tokens"),
                result.get("temperature"),
                result.get("structured_output"),
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

    evaluation = run_and_save_evaluation(version_id, original_text, generated_text, description)

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
        "source_document_id": document_id,
        "parent_version_id": parent_version_id or None,
        "target_page": resolved_page,
        "model": result.get("model"),
        "prompt_version": result.get("prompt_version"),
        "temperature": result.get("temperature"),
        "structured_output": result.get("structured_output"),
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "created_at": created_version,
        "safety_evaluation": evaluation,
    }


def insert_numbered_version(document_id, values, attempts=3):
    """Insert a version as MAX(version_number) + 1 and return that number.

    BEGIN IMMEDIATE takes SQLite's write lock before the MAX() read, so concurrent
    generations (each already paid for) are numbered one after another instead of
    colliding. UNIQUE(document_id, version_number) is the backstop; retry if it fires.
    """
    for attempt in range(attempts):
        connection = connect_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            next_version = connection.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 FROM versions WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO versions
                    (id, document_id, request_id, content, created_at, source_document_id,
                     parent_version_id, target_page, model, prompt_version, input_tokens,
                     output_tokens, temperature, structured_output, version_number, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')
                """,
                (*values, next_version),
            )
            connection.commit()
            return next_version
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            if "UNIQUE" not in str(exc) or attempt == attempts - 1:
                raise
        finally:
            connection.close()


def run_and_save_evaluation(version_id, original_text, generated_text, change_request):
    """Run the automated checks and store them. An evaluator crash must not lose the saved draft."""
    evaluation_id = str(uuid.uuid4())
    created = now()
    try:
        evaluation = evaluate_revision(original_text, generated_text, change_request)
        with connect_db() as connection:
            connection.execute(
                """
                INSERT INTO evaluations
                    (id, version_id, status, metrics_json, findings_json,
                     evaluator_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation_id,
                    version_id,
                    evaluation["status"],
                    json.dumps(evaluation["metrics"]),
                    json.dumps(evaluation["findings"]),
                    evaluation["evaluator_version"],
                    created,
                ),
            )
    except Exception as exc:
        logger.exception("Safety evaluation failed for version %s", version_id)
        return {
            "status": "error",
            "message": f"Automated evaluation failed ({type(exc).__name__}). The draft was saved "
                       "but has NOT been evaluated. Review it manually.",
        }
    return {"id": evaluation_id, "created_at": created, **evaluation, "message": evaluation["disclaimer"]}


def load_version_source(version_id):
    """Return the version row and the original-PDF text it was generated from."""
    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT v.content, v.target_page, v.version_number, d.stored_path, d.filename,
                   cr.description, cr.scope
            FROM versions v
            JOIN documents d ON d.id = v.document_id
            LEFT JOIN change_requests cr ON cr.id = v.request_id
            WHERE v.id = ?
            """,
            (version_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Version not found.")

    scope = row["scope"] or "full"
    if scope == "page" and row["target_page"] is None:
        raise HTTPException(
            status_code=422,
            detail="This page-scoped version predates page tracking, so its source page is unknown.",
        )
    original_text, _ = extract_document_text(row["stored_path"], scope, row["target_page"])
    return row, original_text


@app.post("/api/versions/{version_id}/evaluate")
def evaluate_version(version_id: str):
    """Re-run the automated checks, e.g. for versions created before the evaluator existed."""
    row, original_text = load_version_source(version_id)
    return run_and_save_evaluation(version_id, original_text, row["content"], row["description"] or "")


@app.get("/api/versions/{version_id}/diff")
def diff_version(version_id: str):
    """Line diff of the original text against the draft section, for side-by-side review."""
    row, original_text = load_version_source(version_id)
    draft, _ = extract_draft_section(row["content"])
    original_lines = text_lines(original_text)
    draft_lines = text_lines(draft)

    blocks = []
    matcher = difflib.SequenceMatcher(a=original_lines, b=draft_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        blocks.append({"tag": tag, "original": original_lines[i1:i2], "draft": draft_lines[j1:j2]})
    return {
        "version_id": version_id,
        "blocks": blocks,
        "source_warnings": extract_warnings(original_text),
        "similarity": round(matcher.ratio(), 4),
    }


@app.get("/api/versions/{version_id}/evaluations")
def list_evaluations(version_id: str):
    with connect_db() as connection:
        rows = connection.execute(
            """
            SELECT * FROM evaluations
            WHERE version_id = ?
            ORDER BY created_at DESC
            """,
            (version_id,),
        ).fetchall()

    evaluations = []
    for row in rows:
        item = dict(row)
        item["metrics"] = json.loads(item.pop("metrics_json"))
        item["findings"] = json.loads(item.pop("findings_json"))
        evaluations.append(item)
    return {"evaluations": evaluations}


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
            SELECT v.id, v.document_id, v.request_id, v.version_number, v.status,
                   v.created_at, length(v.content) AS characters,
                   v.source_document_id, v.parent_version_id, v.target_page,
                   v.model, v.prompt_version, v.input_tokens, v.output_tokens,
                   v.temperature, v.structured_output,
                   cr.description AS change_request, cr.scope,
                   (SELECT e.status FROM evaluations e WHERE e.version_id = v.id
                    ORDER BY e.created_at DESC LIMIT 1) AS evaluation_status
            FROM versions v
            LEFT JOIN change_requests cr ON cr.id = v.request_id
            WHERE v.document_id = ?
            ORDER BY v.version_number DESC
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


def render_draft_pdf(header_lines, content):
    """Flow the draft text across A4 pages. This is a text rendering of the draft,
    not a reconstruction of the original PDF layout."""
    body = "".join(
        f"<p>{html.escape(line) or '&nbsp;'}</p>" for line in content.splitlines()
    )
    header = "".join(f"<p><b>{html.escape(line)}</b></p>" for line in header_lines)
    story = pymupdf.Story(
        html=f"{header}<hr/>{body}",
        user_css="p { font-family: sans-serif; font-size: 10pt; margin: 0 0 3pt 0; }",
    )
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    page = pymupdf.paper_rect("a4")
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(page + (50, 50, -50, -50))
        story.draw(device)
        writer.end_page()
    writer.close()
    return buffer.getvalue()


@app.get("/api/versions/{version_id}/download")
def download_version(version_id: str, format: str = "txt"):
    if format not in {"txt", "pdf"}:
        raise HTTPException(status_code=400, detail="format must be 'txt' or 'pdf'.")

    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT v.version_number, v.content, v.created_at, v.status, d.filename,
                   (SELECT e.status FROM evaluations e WHERE e.version_id = v.id
                    ORDER BY e.created_at DESC LIMIT 1) AS evaluation_status
            FROM versions v JOIN documents d ON d.id = v.document_id
            WHERE v.id = ?
            """,
            (version_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Version not found.")

    filename = f"SafeSOP-v{row['version_number']}.{format}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if format == "txt":
        return Response(row["content"], media_type="text/plain; charset=utf-8", headers=headers)

    header_lines = [
        f"AI-GENERATED DRAFT - version {row['version_number']} - review status: {row['status']}",
        f"Source: {row['filename']} (original PDF unchanged) - generated {row['created_at'][:16].replace('T', ' ')} UTC",
        f"Automated check: {row['evaluation_status'] or 'not run'}. "
        "Not valid for use until approved by a qualified reviewer.",
    ]
    return Response(render_draft_pdf(header_lines, row["content"]), media_type="application/pdf",
                    headers=headers)


@app.post("/api/versions/{version_id}/reviews")
def create_review(
    version_id: str,
    decision: str = Form(...),
    reviewer: str = Form("", max_length=MAX_REVIEWER_CHARS),
    feedback: str = Form("", max_length=MAX_FEEDBACK_CHARS),
):
    """Record a human review decision. Only this endpoint changes a version's status."""
    decision = decision.strip().lower()
    reviewer = reviewer.strip()
    feedback = feedback.strip()
    if decision not in REVIEW_DECISIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Decision must be one of: {', '.join(sorted(REVIEW_DECISIONS))}.",
        )
    if not reviewer:
        raise HTTPException(status_code=400, detail="Enter the reviewer's name.")

    review_id = str(uuid.uuid4())
    created = now()
    with connect_db() as connection:
        version = connection.execute(
            "SELECT status FROM versions WHERE id = ?", (version_id,)
        ).fetchone()
        if not version:
            raise HTTPException(status_code=404, detail="Version not found.")
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


@app.get("/api/versions/{version_id}/reviews")
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


@app.get("/api/evaluation/status")
def evaluation_status():
    return {
        "status": "enabled",
        "evaluator_version": EVALUATOR_VERSION,
        "message": (
            "Every generated draft is automatically checked for warning preservation, "
            "unsupported instructions and values, step order, and omitted, altered, "
            "duplicated or conflicting steps. Automated checks are not safety approval."
        ),
    }
