"""documents.ocr_pages: how many pages had no selectable text (scanned) and are read by OCR.

Revision ID: 0007_ocr_pages
Revises: 0006_translations
Create Date: 2026-10-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_ocr_pages"
down_revision = "0006_translations"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("ocr_pages", sa.Integer, nullable=True))


def downgrade():
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("ocr_pages")
