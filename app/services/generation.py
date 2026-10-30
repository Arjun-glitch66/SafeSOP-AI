"""Draft generation: always from the unchanged original PDF, numbered atomically."""
import hashlib
import json
import logging
import uuid

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app import config
from app.audit import append_audit
from app.db import connect_db, now
from app.services.evaluation import run_and_save_evaluation
from app.services.pdf import extract_document_text
from app.services.sections import locate, part_text, splice
from app.storage import resolve
from src.safety_evaluator import extract_draft_section
from src.sop_generator import generate_sop, render_part_lines, render_summaries

logger = logging.getLogger("safesop")

SCOPES = {"full", "page", "section", "step"}
PART_SCOPES = {"section", "step"}


def generate_version(document_id, description, scope, target_page, parent_version_id, request_id, created_by,
                     target_section=None):
    """
    Generate and save an AI draft in the calling thread. This is not safety approval.
    The API runs the same two steps with run_generation() on a background worker.
    """
    return run_generation(prepare_generation(document_id, description, scope, target_page, parent_version_id,
                                             request_id, created_by, target_section))


def prepare_generation(document_id, description, scope, target_page, parent_version_id, request_id, created_by,
                       target_section=None):
    """
    Everything that can fail fast, before the (slow, billed) model call: input checks, limits,
    reading the original PDF and recording the change request. Raises HTTPException 4xx.
    The original PDF remains unchanged and is always the generation source;
    parent_version_id only records which earlier draft this one revises.
    With request_id, the saved change request supplies the description, scope and
    target page (submitted values for those are ignored) and is linked to the draft.
    """
    review_feedback = None
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
            # Reviewers' comments on the draft being revised go to the model with the request.
            parent_reviews = connection.execute(
                """SELECT decision, reviewer, feedback FROM review_history
                   WHERE version_id = ? AND feedback != '' ORDER BY created_at""",
                (parent_version_id,),
            ).fetchall()
            review_feedback = "\n".join(
                f"- {row['reviewer']} ({row['decision'].replace('_', ' ')}): {row['feedback']}" for row in parent_reviews
            ) or None

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
        description, scope, target_page, target_section = (
            saved_request["description"], saved_request["scope"], saved_request["target_page"],
            saved_request["target_section"],
        )

    description = (description or "").strip()
    scope = scope.strip().lower()
    if not description:
        raise HTTPException(status_code=400, detail="Describe the process change.")
    if scope not in SCOPES:
        raise HTTPException(status_code=400, detail="Scope must be 'full', 'page', 'section' or 'step'.")
    target_section = (target_section or "").strip().upper() or None
    if scope in PART_SCOPES and not target_section:
        raise HTTPException(status_code=400, detail=f"For {scope} scope, choose target_section (see the document outline).")

    original_path = resolve(document["stored_path"])
    if not original_path.is_file():
        raise HTTPException(status_code=404, detail="Original PDF file is missing.")

    span = None
    if scope in PART_SCOPES:
        # Only the target part goes to the model; the rest is spliced back unchanged afterwards.
        full_text, _ = extract_document_text(str(original_path), "full", None, max_pages=config.MAX_PDF_PAGES)
        span = locate(full_text, scope, target_section)
        original_text, resolved_page = part_text(full_text, *span[:2]), None
    else:
        original_text, resolved_page = extract_document_text(
            str(original_path), scope, target_page, max_pages=config.MAX_PDF_PAGES
        )
        full_text = original_text
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
                    (id, document_id, description, scope, target_page, target_section, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (request_id, document_id, description, scope, resolved_page, target_section, now()),
            )

    return {
        "document_id": document_id, "filename": document["filename"], "document_type": document["document_type"],
        "description": description, "scope": scope, "target_section": target_section,
        "full_text": full_text, "span": span,
        "original_text": original_text, "resolved_page": resolved_page, "parent_version_id": parent_version_id or None,
        "request_id": request_id, "review_feedback": review_feedback, "created_by": created_by,
    }


def run_generation(prepared, progress=lambda stage: None):
    """The model call, saving the version and the automated checks. `progress(stage)` reports
    'generating', 'saving' and 'evaluating'. Raises HTTPException (502 model, 500 save)."""
    document_id, description, scope = prepared["document_id"], prepared["description"], prepared["scope"]
    original_text, resolved_page = prepared["original_text"], prepared["resolved_page"]
    parent_version_id, request_id = prepared["parent_version_id"], prepared["request_id"]
    review_feedback, created_by = prepared["review_feedback"], prepared["created_by"]

    progress("generating")
    try:
        result = generate_sop(
            original_text=original_text,
            change_request=description,
            output_scope=scope,
            target_page=resolved_page,
            target_section=prepared["target_section"],
            feedback=review_feedback,
        )
    except Exception as exc:
        logger.exception("Gemini SOP generation failed for document %s", document_id)
        # Keep the request record for troubleshooting, but do not create a fake version.
        # RuntimeErrors come from sop_generator's own config checks and contain no secrets.
        reason = str(exc) if isinstance(exc, RuntimeError) else (
            f"{type(exc).__name__}. Check the backend terminal and Gemini model/quota settings."
        )
        raise HTTPException(status_code=502, detail=f"AI generation failed: {reason}") from exc

    progress("saving")
    generated_text = result["text"]
    evaluate_against, evaluate_structured = original_text, result.get("structured")
    if prepared["span"]:
        # Section/step scope: the stored draft is the whole document with only the target part
        # replaced. Checks compare whole documents; the model's source ids are local to the part,
        # so the text path is used.
        start, end, first_step = prepared["span"]
        structured = result.get("structured")
        revised = ("\n".join(render_part_lines(structured, first_step)) if structured
                   else extract_draft_section(result["text"])[0])
        generated_text = "DRAFT:\n" + splice(prepared["full_text"], start, end, revised)
        if structured:
            generated_text += "\n\n" + render_summaries(structured)
        evaluate_against, evaluate_structured = prepared["full_text"], None
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
                created_by,
                prepared["target_section"],
                result.get("provider"),
                int(bool(result.get("fallback_used"))),
                result.get("fallback_reason"),
            ),
            audit={"user": created_by, "version_id": version_id, "payload": {
                "document_id": document_id, "request_id": request_id, "parent_version_id": parent_version_id or None,
                "model": result.get("model"), "prompt_version": result.get("prompt_version"),
                "provider": result.get("provider"), "fallback_used": bool(result.get("fallback_used")),
                "fallback_reason": result.get("fallback_reason"),
                "content_sha256": hashlib.sha256(generated_text.encode("utf-8")).hexdigest(),
            }},
        )
    except Exception as exc:
        logger.exception("Could not save generated version")
        raise HTTPException(
            status_code=500,
            detail="Gemini generated a response, but saving the draft failed. "
                   "Check the backend terminal.",
        ) from exc

    progress("evaluating")
    evaluation = run_and_save_evaluation(version_id, evaluate_against, generated_text, description,
                                         evaluate_structured, resolved_page, prepared["document_type"])

    return {
        "id": version_id,
        "version_id": version_id,
        "document_id": document_id,
        "request_id": request_id,
        "version_number": next_version,
        "filename": prepared["filename"],
        "content": generated_text,
        "status": "draft",
        "ai_provider": "Google Gemini",
        "source_document_id": document_id,
        "parent_version_id": parent_version_id or None,
        "target_page": resolved_page,
        "target_section": prepared["target_section"],
        "model": result.get("model"),
        "prompt_version": result.get("prompt_version"),
        "temperature": result.get("temperature"),
        "structured_output": result.get("structured_output"),
        "structured": result.get("structured"),
        "created_by": created_by,
        "provider": result.get("provider"),
        "fallback_used": bool(result.get("fallback_used")),
        "fallback_reason": result.get("fallback_reason"),
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "created_at": created_version,
        "safety_evaluation": evaluation,
    }


def insert_numbered_version(document_id, values, audit, attempts=3):
    """Insert a version as MAX(version_number) + 1 and return that number.

    lock_writes() (BEGIN IMMEDIATE / an advisory lock) is taken before the MAX() read, so concurrent
    generations (each already paid for) are numbered one after another instead of
    colliding. UNIQUE(document_id, version_number) is the backstop; retry if it fires.
    """
    for attempt in range(attempts):
        connection = connect_db()
        try:
            connection.lock_writes()
            next_version = connection.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 FROM versions WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO versions
                    (id, document_id, request_id, content, created_at, source_document_id,
                     parent_version_id, target_page, model, prompt_version, input_tokens,
                     output_tokens, temperature, structured_output, structured_json, created_by,
                     target_section, provider, fallback_used, fallback_reason, version_number, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')
                """,
                (*values, next_version),
            )
            append_audit(connection, audit["user"], "version_generated", "version", audit["version_id"],
                         {**audit["payload"], "version_number": next_version})
            connection.commit()
            return next_version
        except IntegrityError as exc:
            connection.rollback()
            if "UNIQUE" not in str(exc).upper() or attempt == attempts - 1:
                raise
        finally:
            connection.close()
