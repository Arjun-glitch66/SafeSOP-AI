"""Generating, listing, comparing, evaluating and downloading versions."""
import difflib
import json

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import Response

from app import config
from app.auth import require_role
from app.db import connect_db
from app.services.evaluation import load_version_source, run_and_save_evaluation
from app.services.generation import generate_version
from app.services.pdf import render_draft_pdf
from src.safety_evaluator import extract_draft_section, extract_warnings, text_lines

router = APIRouter()


@router.post("/api/documents/{document_id}/generate")
def generate_revision(
    document_id: str,
    description: str | None = Form(None, max_length=config.MAX_DESCRIPTION_CHARS),
    scope: str = Form("full"),
    target_page: int | None = Form(None),
    parent_version_id: str | None = Form(None),
    request_id: str | None = Form(None),
    user=Depends(require_role("author")),
):
    """
    Generate and save an AI draft. This is not safety approval.
    The original PDF remains unchanged and is always the generation source;
    parent_version_id only records which earlier draft this one revises.
    With request_id, the saved change request supplies the description, scope and
    target page (submitted values for those are ignored) and is linked to the draft.
    """
    return generate_version(document_id, description, scope, target_page, parent_version_id, request_id,
                            created_by=user["username"])


@router.post("/api/versions/{version_id}/evaluate")
def evaluate_version(version_id: str):
    """Re-run the automated checks, e.g. for versions created before the evaluator existed."""
    row, original_text = load_version_source(version_id)
    structured = json.loads(row["structured_json"]) if row["structured_json"] else None
    return run_and_save_evaluation(version_id, original_text, row["content"], row["description"] or "", structured,
                                   row["target_page"])


@router.get("/api/versions/{version_id}/diff")
def diff_version(version_id: str):
    """Line diff of the original text against the draft section, for side-by-side review."""
    row, original_text = load_version_source(version_id)
    draft, _ = extract_draft_section(row["content"])
    original_lines = text_lines(original_text)
    draft_lines = text_lines(draft)

    blocks = []
    matcher = difflib.SequenceMatcher(a=original_lines, b=draft_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        # *_start: 1-based line number of the block's first line, the numbering findings use.
        blocks.append({"tag": tag, "original": original_lines[i1:i2], "draft": draft_lines[j1:j2],
                       "original_start": i1 + 1, "draft_start": j1 + 1})
    return {
        "version_id": version_id,
        "blocks": blocks,
        "source_warnings": extract_warnings(original_text),
        "similarity": round(matcher.ratio(), 4),
    }


@router.get("/api/versions/{version_id}/evaluations")
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


@router.get("/api/documents/{document_id}/versions")
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


@router.get("/api/versions/{version_id}")
def get_version(version_id: str):
    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT v.*, cr.description AS change_request, cr.scope, d.filename,
                   (SELECT e.status FROM evaluations e WHERE e.version_id = v.id
                    ORDER BY e.created_at DESC LIMIT 1) AS evaluation_status
            FROM versions v
            JOIN documents d ON d.id = v.document_id
            LEFT JOIN change_requests cr ON cr.id = v.request_id
            WHERE v.id = ?
            """,
            (version_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Version not found.")

    result = dict(row)
    result.pop("content", None)
    return result


@router.get("/api/versions/{version_id}/content")
def get_version_content(version_id: str):
    with connect_db() as connection:
        row = connection.execute(
            "SELECT content FROM versions WHERE id = ?",
            (version_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Version not found.")
    return {"version_id": version_id, "content": row["content"]}


@router.get("/api/versions/{version_id}/download")
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
