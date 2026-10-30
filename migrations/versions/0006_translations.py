"""Regional-language output: the language, the translated draft, and its independent
back-translation used for the check.

Revision ID: 0006_translations
Revises: 0005_target_section
Create Date: 2026-10-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_translations"
down_revision = "0005_target_section"
branch_labels = None
depends_on = None

COLUMNS = ("output_language", "translated_content", "back_translation")


def upgrade():
    with op.batch_alter_table("versions") as batch:
        for name in COLUMNS:
            batch.add_column(sa.Column(name, sa.Text, nullable=True))


def downgrade():
    with op.batch_alter_table("versions") as batch:
        for name in COLUMNS:
            batch.drop_column(name)
