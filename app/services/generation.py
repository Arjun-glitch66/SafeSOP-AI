"""Draft generation: always from the unchanged original PDF, numbered atomically."""
import json
import logging
import sqlite3
import uuid
from pathlib import Path

from fastapi import HTTPException

from app import config
from app.db import connect_db, now
from app.services.evaluation import run_and_save_evaluation
from app.services.pdf import extract_document_text
from src.sop_generator import generate_sop

logger = logging.getLogger("safesop")


def generate_version(document_id, description, scope, target_page, parent_version_id, request_id):
    """
    Generate and save an AI draft. This is not safety approval.
    The original PDF remains unchanged and is always the generation source;
    parent_version_id only records which earlier draft this one revises.
    With request_id, the saved change request supplies the description, scope and
    target page (submitted values for those are ignored) and is linked to the draft.
    """
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

        saved_request = None
        if request_id:
            saved_request = connection.execute(
                "SELECT * FROM change_requests WHERE id = ? AND document_id = ?",
                (request_id, document_id),
            ).fetchone()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    if parent_version_id and not parent:
        raise HTTPException(
            status_code=400,
            detail="parent_version_id must be a version of this document.",
        )
    if request_id and not saved_request:
        raise HTTPException(
            status_code=400,
            detail="request_id must be a saved change request for this document.",
        )
    if saved_request:
        description, scope, target_page = (
            saved_request["description"], saved_request["scope"], saved_request["target_page"]
        )

    description = (description or "").strip()
    scope = scope.strip().lower()
    if not description:
        raise HTTPException(status_code=400, detail="Describe the process change.")
    if scope not in {"full", "page"}:
        raise HTTPException(status_code=400, detail="Scope must be 'full' or 'page'.")

    original_path = Path(document["stored_path"])
    if not original_path.is_file():
        raise HTTPException(status_code=404, detail="Original PDF file is missing.")

    original_text, resolved_page = extract_document_text(
        str(original_path), scope, target_page, max_pages=config.MAX_PDF_PAGES
    )
    if len(original_text) > config.MAX_SOURCE_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"The source text is {len(original_text):,} characters; the limit is "
                   f"{config.MAX_SOURCE_CHARS:,}. Revise one page at a time instead.",
        )

    # Record the request before calling the provider so the requested change is auditable.
    if not saved_request:
        request_id = str(uuid.uuid4())
        with connect_db() as connection:
            connection.execute(
                """
                INSERT INTO change_requests
                    (id, document_id, description, scope, target_page, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (request_id, document_id, description, scope, resolved_page, now()),
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

    try:
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
                json.dumps(result["structured"]) if result.get("structured") else None,
            ),
        )
    except Exception as exc:
        logger.exception("Could not save generated version")
        raise HTTPException(
            status_code=500,
            detail="Gemini generated a response, but saving the draft failed. "
                   "Check the backend terminal.",
        ) from exc

    evaluation = run_and_save_evaluation(version_id, original_text, generated_text, description,
                                         result.get("structured"))

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
        "structured": result.get("structured"),
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
                     output_tokens, temperature, structured_output, structured_json, version_number, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')
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
