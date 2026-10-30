"""target_section on change requests and versions: the section (SEC1..) or step (S1..) id
revised by section- or step-scoped drafts.

Revision ID: 0005_target_section
Revises: 0004_document_type
Create Date: 2026-10-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_target_section"
down_revision = "0004_document_type"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("change_requests", "versions"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("target_section", sa.Text, nullable=True))


def downgrade():
    for table in ("change_requests", "versions"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("target_section")
