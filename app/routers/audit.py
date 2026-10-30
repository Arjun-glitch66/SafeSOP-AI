"""Reading and verifying the hash-chained audit log."""
import json

from fastapi import APIRouter, Depends

from app.audit import verify_chain
from app.auth import require_role
from app.db import connect_db
from app.pagination import page_params, paginate

router = APIRouter()


@router.get("/api/audit/verify")
def verify_audit_log():
    """Recompute the whole hash chain. ok=false names the first event that does not check out."""
    with connect_db() as connection:
        return verify_chain(connection)


@router.get("/api/audit")
def list_audit_events(page=Depends(page_params), _admin=Depends(require_role("admin"))):
    with connect_db() as connection:
        listed = paginate(connection, "SELECT * FROM audit_events ORDER BY seq DESC", (), page, "events")
    listed["events"] = [{**event, "payload": json.loads(event["payload_json"])} for event in listed["events"]]
    return listed
