"""Running and storing the automated checks for a version."""
import json
import logging
import re
import uuid

from fastapi import HTTPException

from app.db import connect_db, now
from app.services.pdf import extract_document_text
from app.storage import resolve
from src.safety_evaluator import evaluate_revision, evaluate_structured_revision, text_lines
from src.semantic_checker import apply_semantic_check

logger = logging.getLogger("safesop")
PAGE_MARKER = re.compile(r"\[PAGE (\d+)\]")


def add_source_pages(findings, original_text, target_page=None):
    """The original PDF page of each finding's source line: the target page for page-scoped
    versions, else the nearest '[PAGE n]' marker that extract_document_text() put above it."""
    page_of_line, page = [], target_page
    for line in text_lines(original_text):
        marker = PAGE_MARKER.fullmatch(line)
        if marker and target_page is None:
            page = int(marker.group(1))
        page_of_line.append(page)
    for finding in findings:
        line = finding.get("source_line")
        finding["source_page"] = page_of_line[line - 1] if line and line <= len(page_of_line) else None
    return findings


def run_and_save_evaluation(version_id, original_text, generated_text, change_request, structured=None,
                            target_page=None, document_type=None):
    """Run the automated checks and store them. An evaluator crash must not lose the saved draft.
    Prompt-v3 drafts (with structured JSON) are matched by source id; older ones by text."""
    evaluation_id = str(uuid.uuid4())
    created = now()
    try:
        if structured:
            evaluation = evaluate_structured_revision(original_text, generated_text, structured, change_request,
                                                      document_type)
        else:
            evaluation = evaluate_revision(original_text, generated_text, change_request, document_type)
        # Off unless SEMANTIC_CHECK=nli|llm. Advisory: may add findings / raise status, never lower it.
        evaluation = apply_semantic_check(evaluation, original_text, generated_text)
        add_source_pages(evaluation["findings"], original_text, target_page)
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
            SELECT v.content, v.target_page, v.version_number, v.structured_json, d.stored_path, d.filename, d.document_type,
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
    original_text, _ = extract_document_text(str(resolve(row["stored_path"])), scope, row["target_page"])
    return row, original_text
