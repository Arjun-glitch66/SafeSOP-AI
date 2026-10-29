
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
DATABASE_PATH = DATA_DIR / "safesop.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with get_connection() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_name TEXT NOT NULL,
                original_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS generation_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                change_request TEXT NOT NULL,
                output_scope TEXT NOT NULL,
                target_page INTEGER,
                target_section TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (document_id)
                    REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                request_id INTEGER,
                version_number INTEGER NOT NULL,
                version_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                content TEXT,
                parent_version_id INTEGER,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                UNIQUE (document_id, version_number),
                FOREIGN KEY (document_id)
                    REFERENCES documents(id),
                FOREIGN KEY (request_id)
                    REFERENCES generation_requests(id),
                FOREIGN KEY (parent_version_id)
                    REFERENCES versions(id)
            );

            CREATE TABLE IF NOT EXISTS evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                version_id INTEGER NOT NULL,
                metrics_json TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (document_id)
                    REFERENCES documents(id),
                FOREIGN KEY (version_id)
                    REFERENCES versions(id)
            );

            CREATE TABLE IF NOT EXISTS review_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id INTEGER NOT NULL,
                decision TEXT NOT NULL,
                feedback TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (version_id)
                    REFERENCES versions(id)
            );
        """)


def current_time():
    return datetime.now(timezone.utc).isoformat()


def register_original(original_name, original_path, file_hash):
    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT INTO documents
            (original_name, original_path, file_hash, created_at)
            VALUES (?, ?, ?, ?)
        """, (original_name, str(original_path), file_hash, current_time()))

        return cursor.lastrowid


def create_generation_request(
    document_id,
    change_request,
    output_scope,
    target_page=None,
    target_section=None
):
    allowed_scopes = ("full", "page", "section", "step")

    if output_scope not in allowed_scopes:
        raise ValueError("Invalid output scope")

    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT INTO generation_requests
            (document_id, change_request, output_scope,
             target_page, target_section, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            document_id,
            change_request,
            output_scope,
            target_page,
            target_section,
            current_time()
        ))

        return cursor.lastrowid


def save_version(
    document_id,
    version_name,
    file_path,
    content,
    request_id=None,
    parent_version_id=None
):
    with get_connection() as connection:
        document = connection.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document_id,)
        ).fetchone()

        if document is None:
            raise ValueError("Original document does not exist")

        result = connection.execute("""
            SELECT COALESCE(MAX(version_number), 0) + 1 AS next_number
            FROM versions
            WHERE document_id = ?
        """, (document_id,)).fetchone()

        version_number = result["next_number"]

        cursor = connection.execute("""
            INSERT INTO versions
            (document_id, request_id, version_number,
             version_name, file_path, content,
             parent_version_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?)
        """, (
            document_id,
            request_id,
            version_number,
            version_name,
            str(file_path),
            content,
            parent_version_id,
            current_time()
        ))

        return cursor.lastrowid


def save_evaluation(
    document_id,
    version_id,
    metrics,
    findings,
    status
):
    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT INTO evaluations
            (document_id, version_id, metrics_json,
             findings_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            document_id,
            version_id,
            json.dumps(metrics),
            json.dumps(findings),
            status,
            current_time()
        ))

        return cursor.lastrowid


def save_review(version_id, decision, feedback=""):
    allowed_decisions = (
        "selected", "approved", "rejected", "needs_revision"
    )

    if decision not in allowed_decisions:
        raise ValueError("Invalid review decision")

    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT INTO review_history
            (version_id, decision, feedback, created_at)
            VALUES (?, ?, ?, ?)
        """, (version_id, decision, feedback, current_time()))

        if decision == "approved":
            connection.execute("""
                UPDATE versions
                SET status = 'approved'
                WHERE id = ?
            """, (version_id,))

        elif decision == "rejected":
            connection.execute("""
                UPDATE versions
                SET status = 'rejected'
                WHERE id = ?
            """, (version_id,))

        elif decision == "needs_revision":
            connection.execute("""
                UPDATE versions
                SET status = 'needs_revision'
                WHERE id = ?
            """, (version_id,))

        return cursor.lastrowid


def get_versions(document_id):
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT *
            FROM versions
            WHERE document_id = ?
            ORDER BY version_number ASC
        """, (document_id,)).fetchall()

        return [dict(row) for row in rows]


def get_evaluations(version_id):
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT *
            FROM evaluations
            WHERE version_id = ?
            ORDER BY id ASC
        """, (version_id,)).fetchall()

        results = []

        for row in rows:
            item = dict(row)
            item["metrics"] = json.loads(item.pop("metrics_json"))
            item["findings"] = json.loads(item.pop("findings_json"))
            results.append(item)

        return results


init_db()
