"""Liveness and evaluator status."""
from fastapi import APIRouter

from src.safety_evaluator import EVALUATOR_VERSION

router = APIRouter()


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
