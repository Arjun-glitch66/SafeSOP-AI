"""Background generation jobs: the request returns 202 at once, a worker thread does the slow,
billed model call, and clients follow progress with GET /api/jobs/{id} or its event stream.

ponytail: in-process thread pool. Jobs survive a restart only as records (marked failed at
startup); a multi-instance deployment needs an external queue (e.g. Redis + RQ) instead.
"""
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException

from app import config
from app.db import connect_db, now
from app.services.generation import run_generation

logger = logging.getLogger("safesop")

TERMINAL = {"succeeded", "failed"}
STAGE_TEXT = {
    "queued": "Waiting for a free worker",
    "generating": "Waiting for the model to write the draft",
    "saving": "Saving the draft as a new version",
    "evaluating": "Running the automated checks",
    "done": "Done",
}
_executor = None


def executor():
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=config.GENERATION_WORKERS, thread_name_prefix="generate")
    return _executor


def shutdown():
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None


def update(job_id, **fields):
    fields["updated_at"] = now()
    assignments = ", ".join(f"{name} = ?" for name in fields)  # names come from this module only
    with connect_db() as connection:
        connection.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*fields.values(), job_id))


def submit(prepared):
    job_id = str(uuid.uuid4())
    created = now()
    with connect_db() as connection:
        connection.execute(
            """INSERT INTO jobs (id, kind, document_id, created_by, status, stage, created_at, updated_at)
               VALUES (?, 'generate', ?, ?, 'queued', 'queued', ?, ?)""",
            (job_id, prepared["document_id"], prepared["created_by"], created, created),
        )
    executor().submit(_run, job_id, prepared)
    return get_job(job_id)


def _run(job_id, prepared):
    update(job_id, status="running", stage="generating")
    try:
        result = run_generation(prepared, progress=lambda stage: update(job_id, stage=stage))
    except HTTPException as exc:
        update(job_id, status="failed", stage="done", http_status=exc.status_code, detail=str(exc.detail))
    except Exception as exc:  # never leave a job 'running' forever
        logger.exception("Generation job %s crashed", job_id)
        update(job_id, status="failed", stage="done", http_status=500,
               detail=f"Generation failed on the server: {type(exc).__name__}.")
    else:
        update(job_id, status="succeeded", stage="done", http_status=200, version_id=result["version_id"],
               result_json=json.dumps(result))


def get_job(job_id):
    with connect_db() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found.")
    job = dict(row)
    job["result"] = json.loads(job.pop("result_json")) if job["result_json"] else None
    job["stage_text"] = STAGE_TEXT.get(job["stage"], job["stage"])
    return job


def fail_interrupted_jobs():
    """At startup: jobs a previous process left queued or running will never finish."""
    with connect_db() as connection:
        connection.execute(
            """UPDATE jobs SET status = 'failed', stage = 'done', http_status = 500, updated_at = ?,
                   detail = 'Interrupted by a server restart. Check the version list, then generate again if needed.'
               WHERE status IN ('queued', 'running')""",
            (now(),),
        )
