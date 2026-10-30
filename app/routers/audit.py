"""Reading and verifying the hash-chained audit log."""
import json

from fastapi import APIRouter, Depends

from app.audit import verify_chain
from app.auth import require_role
from app.db import connect_db

router = APIRouter()


@router.get("/api/audit/verify")
def verify_audit_log():
    """Recompute the whole hash chain. ok=false names the first event that does not check out."""
    with connect_db() as connection:
        return verify_chain(connection)


@router.get("/api/audit")
def list_audit_events(limit: int = 200, _admin=Depends(require_role("admin"))):
    with connect_db() as connection:
        rows = connection.execute("SELECT * FROM audit_events ORDER BY seq DESC LIMIT ?", (min(limit, 1000),)).fetchall()
    return {"events": [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]}
