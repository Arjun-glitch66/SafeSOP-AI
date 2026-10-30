"""Generating, listing, comparing, evaluating and downloading versions."""
import asyncio
import difflib
import json
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app import config
from app.auth import require_role
from app.db import connect_db, now
from app.limits import check_generate_allowed
from app.pagination import page_params, paginate
from app.schemas import FINDING_VERDICTS
from app.services import jobs
from app.services.evaluation import load_version_source, run_and_save_evaluation
from app.services.generation import prepare_generation
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
    target_section: str | None = Form(None, max_length=20),
    user=Depends(require_role("author")),
):
    """
    Start generating an AI draft. Input problems are answered at once (4xx); otherwise the
    answer is 202 with a job id, and the slow model call runs in the background. Follow it
    with GET /api/jobs/{job_id} or the event stream at /api/jobs/{job_id}/events.
    The original PDF remains unchanged and is always the generation source;
    parent_version_id only records which earlier draft this one revises.
    With request_id, the saved change request supplies the description, scope and
    target page (submitted values for those are ignored) and is linked to the draft.
    """
    check_generate_allowed(user["username"])  # 429 before any work
    prepared = prepare_generation(document_id, description, scope, target_page, parent_version_id, request_id,
                                  created_by=user["username"], target_section=target_section)
    job = jobs.submit(prepared)
    return JSONResponse(status_code=202, content={
        "job_id": job["id"], "status": job["status"], "stage_text": job["stage_text"],
        "status_url": f"/api/jobs/{job['id']}", "events_url": f"/api/jobs/{job['id']}/events",
    })


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return jobs.get_job(job_id)


@router.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    """Server-sent events: one `progress` event per change, then `succeeded` or `failed`."""
    jobs.get_job(job_id)  # 404 before the stream starts

    async def stream():
        last = None
        for tick in range(int(config.JOB_STREAM_SECONDS / 0.5)):
            job = await asyncio.to_thread(jobs.get_job, job_id)
            state = (job["status"], job["stage"])
            if state != last:
                last = state
                kind = job["status"] if job["status"] in jobs.TERMINAL else "progress"
                yield f"event: {kind}\ndata: {json.dumps(job)}\n\n"
                if kind != "progress":
                    return
            elif tick % 30 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/versions/{version_id}/evaluate")
def evaluate_version(version_id: str):
    """Re-run the automated checks, e.g. for versions created before the evaluator existed."""
    row, original_text = load_version_source(version_id)
    structured = json.loads(row["structured_json"]) if row["structured_json"] else None
    return run_and_save_evaluation(version_id, original_text, row["content"], row["description"] or "", structured,
                                   row["target_page"], row["document_type"])


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
def list_evaluations(version_id: str, page=Depends(page_params)):
    with connect_db() as connection:
        listed = paginate(connection, """
            SELECT * FROM evaluations
            WHERE version_id = ?
            ORDER BY created_at DESC, id
            """, (version_id,), page, "evaluations")
        rows = listed.pop("evaluations")

        verdicts = connection.execute(
            """SELECT f.evaluation_id, f.finding_index, f.verdict, f."user" FROM finding_feedback f
               JOIN evaluations e ON e.id = f.evaluation_id WHERE e.version_id = ? ORDER BY f.created_at""",
            (version_id,),
        ).fetchall()

    evaluations = []
    for row in rows:
        item = dict(row)
        item["metrics"] = json.loads(item.pop("metrics_json"))
        item["findings"] = json.loads(item.pop("findings_json"))
        for index, finding in enumerate(item["findings"]):
            finding["feedback"] = [{"verdict": v["verdict"], "user": v["user"]} for v in verdicts
                                   if v["evaluation_id"] == item["id"] and v["finding_index"] == index]
        evaluations.append(item)
    return {"evaluations": evaluations, **listed}


@router.put("/api/evaluations/{evaluation_id}/findings/{finding_index}/feedback")
def set_finding_feedback(evaluation_id: str, finding_index: int, verdict: str = Form(...),
                         user=Depends(require_role("reviewer"))):
    """A reviewer's verdict on one automated finding: true_problem or false_alarm. One verdict
    per reviewer per finding; sending another replaces it."""
    if verdict not in FINDING_VERDICTS:
        raise HTTPException(status_code=400, detail=f"Verdict must be one of: {', '.join(FINDING_VERDICTS)}.")
    with connect_db() as connection:
        row = connection.execute("SELECT findings_json FROM evaluations WHERE id = ?", (evaluation_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Evaluation not found.")
        findings = json.loads(row["findings_json"])
        if not 0 <= finding_index < len(findings):
            raise HTTPException(status_code=404, detail="Finding not found.")
        connection.execute(
            """INSERT INTO finding_feedback (id, evaluation_id, finding_index, finding_type, verdict, "user", created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(evaluation_id, finding_index, "user")
               DO UPDATE SET verdict = excluded.verdict, created_at = excluded.created_at""",
            (str(uuid.uuid4()), evaluation_id, finding_index, findings[finding_index]["type"], verdict,
             user["username"], now()),
        )
    return {"evaluation_id": evaluation_id, "finding_index": finding_index, "verdict": verdict, "user": user["username"]}


@router.get("/api/documents/{document_id}/versions")
def list_versions(document_id: str, page=Depends(page_params)):
    with connect_db() as connection:
        exists = connection.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Document not found.")

        return paginate(connection, """
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
            """, (document_id,), page, "versions")


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
