"""Database access: a SQLAlchemy engine (SQLite by default, Postgres via DATABASE_URL), a small
connection adapter that keeps the app's plain-SQL style, and schema migrations with Alembic.

connect_db() returns a Connection whose execute() takes '?' placeholders (or :name with a
dict), whose rows support row["col"] and row[0], and which commits on leaving a `with` block
(rolls back on error). Writers that must not interleave (audit chain, version numbering) call
connection.lock_writes() first: BEGIN IMMEDIATE on SQLite, a transaction advisory lock on Postgres.
"""
import logging
import re
import sqlite3
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.pool import NullPool

from app import config

logger = logging.getLogger("safesop")

WRITE_LOCK_KEY = 7262_0001  # pg_advisory_xact_lock key shared by every audited writer
_engines = {}


def now():
    return datetime.now(timezone.utc).isoformat()


def engine():
    """One engine per database URL (tests point DB_PATH at a temporary file per test)."""
    url = config.database_url()
    if url not in _engines:
        if url.startswith("sqlite"):
            created = create_engine(url, poolclass=NullPool, connect_args={"timeout": 10, "check_same_thread": False})

            @event.listens_for(created, "connect")
            def _sqlite_connect(dbapi_connection, _record):
                dbapi_connection.isolation_level = None  # let SQLAlchemy's begin event issue BEGIN
                dbapi_connection.execute("PRAGMA foreign_keys = ON")

            @event.listens_for(created, "begin")
            def _sqlite_begin(connection):
                write = connection.get_execution_options().get("write_lock")
                connection.exec_driver_sql("BEGIN IMMEDIATE" if write else "BEGIN")
        else:
            created = create_engine(url, pool_pre_ping=True)
        _engines[url] = created
    return _engines[url]


class Row(dict):
    """A result row: row["column"] and, like sqlite3.Row, row[0]."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class Result:
    def __init__(self, result):
        self._result = result
        self.rowcount = result.rowcount

    def fetchone(self):
        row = self._result.mappings().fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(row) for row in self._result.mappings().fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


_QMARK = re.compile(r"\?")


class Connection:
    def __init__(self, sa_connection):
        self._connection = sa_connection
        self.dialect = sa_connection.dialect.name

    def lock_writes(self):
        """Serialise writers. Must be the first call in the transaction on SQLite."""
        if self.dialect == "sqlite":
            if self._connection.in_transaction():
                raise RuntimeError("lock_writes() must come before any other statement")
            self._connection.execution_options(write_lock=True)
            self._connection.begin()
        else:
            self._connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": WRITE_LOCK_KEY})

    def execute(self, sql, params=()):
        if isinstance(params, dict):
            statement, bound = sql, params
        else:
            counter = iter(range(len(params)))
            statement = _QMARK.sub(lambda _: f":p{next(counter)}", sql)
            bound = {f"p{index}": value for index, value in enumerate(params)}
        return Result(self._connection.execute(text(statement), bound))

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        try:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
        finally:
            self._connection.close()
        return False


def connect_db():
    return Connection(engine().connect())


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
    # Which LLM produced the draft, and whether the fallback provider had to step in (and why).
    "provider": "TEXT",
    "fallback_used": "INTEGER",
    "fallback_reason": "TEXT",
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
    """Bring the database to the latest schema, keeping all data.

    Schema changes are Alembic revisions (migrations/versions/). SQLite files created before
    Alembic was introduced are first upgraded in place by the original column-adding code
    (with a backup), which brings them to the baseline revision, and are then stamped.
    """
    from alembic import command

    url = config.database_url()
    if url.startswith("sqlite"):
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with engine().connect() as connection:
        tables = set(inspect(connection).get_table_names())
        if "documents" in tables:
            columns = {column["name"] for column in inspect(connection).get_columns("documents")}
            if "stored_path" not in columns:
                # The legacy Streamlit schema (integer IDs) owns this file. Refuse rather than mix schemas.
                raise RuntimeError(
                    f"{config.DB_PATH} uses the legacy Streamlit schema. Move it aside "
                    "(it is not deleted automatically) and restart the API."
                )
    alembic_config = migration_config()
    if "documents" in tables and "alembic_version" not in tables:
        _upgrade_pre_alembic_sqlite()
        command.stamp(alembic_config, BASELINE_REVISION)
        logger.info("Pre-Alembic database upgraded and stamped at %s", BASELINE_REVISION)
    command.upgrade(alembic_config, "head")


BASELINE_REVISION = "0001_baseline"


def migration_config():
    from alembic.config import Config

    alembic_config = Config()
    alembic_config.set_main_option("script_location", str(config.BASE_DIR / "migrations"))
    alembic_config.attributes["engine"] = engine()
    return alembic_config


def _upgrade_pre_alembic_sqlite():
    """The schema code used before Alembic, unchanged: creates missing tables, adds missing
    columns (after a backup when the database has data) and backfills lineage. It produces
    exactly the baseline revision's schema."""
    connection = sqlite3.connect(config.DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            _legacy_schema(connection)
    finally:
        connection.close()


def _legacy_schema(connection):
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

            -- Reviewers' verdicts on individual automated findings: labelled data for the benchmark.
            CREATE TABLE IF NOT EXISTS finding_feedback (
                id TEXT PRIMARY KEY,
                evaluation_id TEXT NOT NULL,
                finding_index INTEGER NOT NULL,
                finding_type TEXT NOT NULL,
                verdict TEXT NOT NULL CHECK (verdict IN ('true_problem', 'false_alarm')),
                user TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(evaluation_id) REFERENCES evaluations(id),
                UNIQUE(evaluation_id, finding_index, user)
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                document_id TEXT NOT NULL,
                created_by TEXT NOT NULL,
                status TEXT NOT NULL,          -- queued | running | succeeded | failed
                stage TEXT NOT NULL,           -- queued | generating | saving | evaluating | done
                http_status INTEGER,
                detail TEXT,
                version_id TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            );

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
    connection.execute(
        "UPDATE versions SET source_document_id = document_id WHERE source_document_id IS NULL"
    )
