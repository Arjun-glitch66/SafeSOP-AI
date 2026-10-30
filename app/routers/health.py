"""Liveness and evaluator status."""
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import config
from app.db import connect_db

from src.safety_evaluator import EVALUATOR_VERSION

router = APIRouter()


@router.get("/healthz")
def liveness():
    """The process is up. No dependencies are checked, so a slow database never restarts it."""
    return {"status": "alive"}


@router.get("/readyz")
def readiness():
    """Ready to serve: the database answers and the file store is writable. 503 otherwise."""
    checks = {}
    try:
        with connect_db() as connection:
            connection.execute("SELECT 1").fetchone()
        checks["database"] = "ok"
    except Exception as exc:  # report, do not raise: the orchestrator needs the 503
        checks["database"] = f"error: {type(exc).__name__}"
    try:
        config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        probe = config.UPLOAD_DIR / f".ready-{os.getpid()}"
        probe.write_bytes(b"ok")
        probe.unlink()
        checks["storage"] = "ok"
    except OSError as exc:
        checks["storage"] = f"error: {type(exc).__name__}"
    ready = all(value == "ok" for value in checks.values())
    return JSONResponse(status_code=200 if ready else 503, content={"status": "ready" if ready else "not ready", **checks})


@router.get("/")
def root():
    return {
        "name": "SafeSOP AI API",
        "status": "running",
        "docs": "/docs",
    }


@router.get("/api/health")
def health():
    return {"status": "healthy", "service": "SafeSOP AI"}


@router.get("/api/evaluation/status")
def evaluation_status():
    return {
        "status": "enabled",
        "evaluator_version": EVALUATOR_VERSION,
        "message": (
            "Every generated draft is automatically checked for warning preservation, "
            "unsupported instructions and values, step order, omitted, altered, duplicated "
            "or conflicting steps, steps that contradict a warning, weakened quantifiers, "
            "changed actors and change requests that were not applied. Automated checks "
            "are not safety approval."
        ),
    }
