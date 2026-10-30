import sqlite3

import pytest

import api

OLD_SCHEMA = """
CREATE TABLE documents (id TEXT PRIMARY KEY, filename TEXT NOT NULL, stored_path TEXT NOT NULL,
    sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE change_requests (id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
    description TEXT NOT NULL, scope TEXT NOT NULL DEFAULT 'full', created_at TEXT NOT NULL);
CREATE TABLE versions (id TEXT PRIMARY KEY, document_id TEXT NOT NULL, request_id TEXT,
    version_number INTEGER NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL, UNIQUE(document_id, version_number));
INSERT INTO documents VALUES ('doc1', 'Arjun 1.pdf', 'x.pdf', 'abc', 10, '2026-10-01');
INSERT INTO change_requests VALUES ('req1', 'doc1', 'add gloves', 'full', '2026-10-01');
INSERT INTO versions VALUES ('ver1', 'doc1', 'req1', 1, 'old draft text', 'draft', '2026-10-01');
"""


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DB_PATH", tmp_path / "safesop.db")
    monkeypatch.setattr(api, "BACKUP_DIR", tmp_path / "backups")
    return tmp_path


def test_old_database_is_backed_up_and_upgraded_without_data_loss(temp_db):
    with sqlite3.connect(api.DB_PATH) as connection:
        connection.executescript(OLD_SCHEMA)

    api.init_db()
    api.init_db()  # running again must be a harmless no-op

    with api.connect_db() as connection:
        row = dict(connection.execute("SELECT * FROM versions WHERE id = 'ver1'").fetchone())
        tables = {r["name"] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        request = dict(connection.execute("SELECT * FROM change_requests WHERE id = 'req1'").fetchone())

    assert row["content"] == "old draft text"
    assert row["source_document_id"] == "doc1"
    assert set(api.VERSION_COLUMNS) <= set(row)
    assert request["description"] == "add gloves" and request["target_page"] is None
    assert {"evaluations", "review_history"} <= tables

    backups = list((temp_db / "backups").glob("*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT content FROM versions").fetchone()[0] == "old draft text"


def test_legacy_streamlit_schema_is_refused_not_modified(temp_db):
    with sqlite3.connect(api.DB_PATH) as connection:
        connection.execute(
            "CREATE TABLE documents (id INTEGER PRIMARY KEY, original_name TEXT, "
            "original_path TEXT, file_hash TEXT, created_at TEXT)"
        )

    with pytest.raises(RuntimeError, match="legacy Streamlit schema"):
        api.init_db()

    with sqlite3.connect(api.DB_PATH) as connection:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"documents"}


def schema(db_path):
    with sqlite3.connect(db_path) as connection:
        tables = [r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        columns = {t: sorted(r[1] for r in connection.execute(f"PRAGMA table_info({t})")) for t in tables}
        indexes = sorted(r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'ix_%'"))
        triggers = sorted(r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'"))
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    return columns, indexes, triggers, version


def test_legacy_upgrade_and_a_fresh_alembic_database_have_the_same_schema(temp_db, monkeypatch, tmp_path):
    with sqlite3.connect(api.DB_PATH) as connection:
        connection.executescript(OLD_SCHEMA)
    api.init_db()
    upgraded = schema(api.DB_PATH)

    monkeypatch.setattr(api, "DB_PATH", tmp_path / "fresh.db")
    api.init_db()
    assert schema(api.DB_PATH) == upgraded
    columns, indexes, triggers, version = upgraded
    assert version == "0003_relative_paths" and "ix_versions_document_id" in indexes
    assert triggers == ["audit_events_no_delete", "audit_events_no_update"]


def test_stored_paths_inside_the_data_folder_become_relative(temp_db, monkeypatch):
    monkeypatch.setattr(api, "DATA_DIR", temp_db)
    inside, outside = temp_db / "originals" / "doc1.pdf", "C:/elsewhere/doc2.pdf"
    with sqlite3.connect(api.DB_PATH) as connection:
        connection.executescript(OLD_SCHEMA.replace("'x.pdf'", f"'{inside.as_posix()}'"))
        connection.execute("INSERT INTO documents VALUES ('doc2', 'b.pdf', ?, 'def', 10, '2026-10-01')", (outside,))
    api.init_db()
    with sqlite3.connect(api.DB_PATH) as connection:
        paths = dict(connection.execute("SELECT id, stored_path FROM documents"))
    assert paths == {"doc1": "originals/doc1.pdf", "doc2": outside}
    assert api.resolve(paths["doc1"]) == temp_db / "originals" / "doc1.pdf"
