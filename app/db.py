"""SQLite connection, schema and the in-place migration (init_db)."""
import logging
import sqlite3
from datetime import datetime, timezone

from app import config

logger = logging.getLogger("safesop")


def now():
    return datetime.now(timezone.utc).isoformat()


def connect_db():
    connection = sqlite3.connect(config.DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# Columns added after the first release. Added with ALTER TABLE so existing rows are kept.
VERSION_COLUMNS = {
    "source_document_id": "TEXT REFERENCES documents(id)",
    "parent_version_id": "TEXT REFERENCES versions(id)",
    "target_page": "INTEGER",
    "model": "TEXT",
    "prompt_version": "TEXT",
    "input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
    "temperature": "REAL",
    "structured_output": "INTEGER",
    # Prompt v3+: the model's JSON (steps/warnings citing source ids). NULL for older versions.
    "structured_json": "TEXT",
    # Username of whoever generated the version (NULL before sign-in existed).
    "created_by": "TEXT",
}


DOCUMENT_COLUMNS = {
    "page_count": "INTEGER",
}


CHANGE_REQUEST_COLUMNS = {
    "target_page": "INTEGER",
}

# What an approval signed: the checks it was shown, the original PDF and the exact draft text.
REVIEW_COLUMNS = {
    "evaluator_version": "TEXT",
    "evaluation_status": "TEXT",
    "source_sha256": "TEXT",
    "content_sha256": "TEXT",
}


def init_db():
    with connect_db() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(documents)")}
        if columns and "stored_path" not in columns:
            # The legacy Streamlit schema (integer IDs) owns this file. Refuse rather than mix schemas.
            raise RuntimeError(
                f"{config.DB_PATH} uses the legacy Streamlit schema. Move it aside "
                "(it is not deleted automatically) and restart the API."
            )

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS change_requests (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                description TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'full',
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS versions (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                request_id TEXT,
                version_number INTEGER NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id),
                FOREIGN KEY(request_id) REFERENCES change_requests(id),
                UNIQUE(document_id, version_number)
            );

            CREATE TABLE IF NOT EXISTS evaluations (
                id TEXT PRIMARY KEY,
                version_id TEXT NOT NULL,
                status TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                evaluator_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(version_id) REFERENCES versions(id)
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL UNIQUE,
                ts TEXT NOT NULL,
                user TEXT NOT NULL,
                action TEXT NOT NULL,
                entity TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                prev_hash TEXT NOT NULL UNIQUE,
                hash TEXT NOT NULL UNIQUE
            );

            -- Append-only: the database itself refuses to change or remove audit events.
            CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
            BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
            BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS review_history (
                id TEXT PRIMARY KEY,
                version_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                reviewer TEXT,
                feedback TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(version_id) REFERENCES versions(id)
            );
            """
        )

        missing = []
        for table, wanted in (("documents", DOCUMENT_COLUMNS), ("versions", VERSION_COLUMNS),
                              ("change_requests", CHANGE_REQUEST_COLUMNS), ("review_history", REVIEW_COLUMNS)):
            existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
            missing += [(table, name, sql) for name, sql in wanted.items() if name not in existing]

        has_rows = connection.execute(
            "SELECT (SELECT COUNT(*) FROM versions) + (SELECT COUNT(*) FROM documents)"
        ).fetchone()[0] > 0
        if missing and has_rows:
            config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup_path = config.BACKUP_DIR / f"safesop-{datetime.now():%Y%m%d-%H%M%S}.db"
            backup = sqlite3.connect(backup_path)
            try:
                connection.backup(backup)
            finally:
                backup.close()
            logger.info("Backed up database to %s before migration", backup_path)

        # Table and column names come from the constants above, never from user input.
        for table, name, sql in missing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql}")
        if missing:
            logger.info("Added columns: %s", ", ".join(f"{t}.{n}" for t, n, _ in missing))

        # Every pre-lineage version was generated from its own document's original PDF.
        # Runs on every start so an interrupted migration still gets backfilled.
        connection.execute(
            "UPDATE versions SET source_document_id = document_id WHERE source_document_id IS NULL"
        )
