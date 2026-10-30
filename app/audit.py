"""Append-only, hash-chained audit log.

Each event stores hash = sha256(prev_hash + canonical JSON of the event), so changing, removing
or reordering any past event breaks every hash after it. SQLite triggers refuse UPDATE and
DELETE on the table; verify_chain() catches tampering that bypasses them (e.g. editing the file).

Events are written with the caller's connection, inside the same transaction as the change
they record. Callers start that transaction with BEGIN IMMEDIATE so two writers cannot read
the same chain head; UNIQUE(prev_hash) is the backstop.
"""
import hashlib
import json
import uuid

from app.db import now

GENESIS = "0" * 64


def canonical(event):
    """The hashed form of an event: every field except the hash, keys sorted, no whitespace."""
    fields = {key: event[key] for key in ("id", "ts", "user", "action", "entity", "entity_id", "payload_json", "prev_hash")}
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def event_hash(event):
    return hashlib.sha256((event["prev_hash"] + canonical(event)).encode("utf-8")).hexdigest()


def append_audit(connection, user, action, entity, entity_id, payload):
    head = connection.execute("SELECT hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
    event = {
        "id": str(uuid.uuid4()), "ts": now(), "user": user, "action": action, "entity": entity,
        "entity_id": entity_id, "payload_json": json.dumps(payload, sort_keys=True, separators=(",", ":")),
        "prev_hash": head["hash"] if head else GENESIS,
    }
    event["hash"] = event_hash(event)
    connection.execute(
        """INSERT INTO audit_events (id, ts, user, action, entity, entity_id, payload_json, prev_hash, hash)
           VALUES (:id, :ts, :user, :action, :entity, :entity_id, :payload_json, :prev_hash, :hash)""",
        event,
    )
    return event


def verify_chain(connection):
    """Recompute every hash in order. Returns ok, the number of events, and the first broken one."""
    expected_prev = GENESIS
    count = 0
    for row in connection.execute("SELECT * FROM audit_events ORDER BY seq"):
        event = dict(row)
        count += 1
        if event["prev_hash"] != expected_prev:
            return {"ok": False, "events": count, "broken_at": event["seq"], "event_id": event["id"],
                    "reason": "prev_hash does not match the previous event (an event was removed, added or reordered)"}
        if event_hash(event) != event["hash"]:
            return {"ok": False, "events": count, "broken_at": event["seq"], "event_id": event["id"],
                    "reason": "hash does not match the event's contents (the event was changed)"}
        expected_prev = event["hash"]
    return {"ok": True, "events": count, "broken_at": None, "head": expected_prev}
