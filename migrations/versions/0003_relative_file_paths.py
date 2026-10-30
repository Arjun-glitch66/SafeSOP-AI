"""Store original-PDF paths relative to the data directory, so the data folder (or a Docker
volume) can move without breaking every document. Paths outside the data directory are kept
as they are; app.storage resolves both forms.

Revision ID: 0003_relative_paths
Revises: 0002_fk_indexes
Create Date: 2026-10-30
"""
from pathlib import Path

import sqlalchemy as sa
from alembic import context, op

from app import config

revision = "0003_relative_paths"
down_revision = "0002_fk_indexes"
branch_labels = None
depends_on = None


def upgrade():
    if context.is_offline_mode():
        return  # data migration: needs the rows, so it only runs against a live database
    connection = op.get_bind()
    data_dir = Path(config.DATA_DIR).resolve()
    rows = connection.execute(sa.text("SELECT id, stored_path FROM documents")).fetchall()
    for document_id, stored_path in rows:
        path = Path(stored_path)
        if not path.is_absolute():
            continue
        try:
            relative = path.resolve().relative_to(data_dir).as_posix()
        except ValueError:
            continue  # outside the data directory: leave it absolute
        connection.execute(sa.text("UPDATE documents SET stored_path = :path WHERE id = :id"),
                           {"path": relative, "id": document_id})


def downgrade():
    connection = op.get_bind()
    data_dir = Path(config.DATA_DIR).resolve()
    rows = connection.execute(sa.text("SELECT id, stored_path FROM documents")).fetchall()
    for document_id, stored_path in rows:
        if not Path(stored_path).is_absolute():
            connection.execute(sa.text("UPDATE documents SET stored_path = :path WHERE id = :id"),
                               {"path": str(data_dir / stored_path), "id": document_id})
