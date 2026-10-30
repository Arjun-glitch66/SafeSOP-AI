"""documents.document_type: which required-element checklist (src/checklists/*.yaml) applies.

Revision ID: 0004_document_type
Revises: 0003_relative_paths
Create Date: 2026-10-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_document_type"
down_revision = "0003_relative_paths"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("document_type", sa.Text, nullable=True))


def downgrade():
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("document_type")
