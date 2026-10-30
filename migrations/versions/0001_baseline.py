"""Baseline: the schema as of phase 3 (identical to what the pre-Alembic init_db produced).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def text_column(name, *args, nullable=True, **kwargs):
    return sa.Column(name, sa.Text, *args, nullable=nullable, **kwargs)


def upgrade():
    op.create_table(
        "documents",
        text_column("id", primary_key=True),
        text_column("filename", nullable=False),
        text_column("stored_path", nullable=False),
        text_column("sha256", nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        text_column("created_at", nullable=False),
        sa.Column("page_count", sa.Integer),
    )
    op.create_table(
        "change_requests",
        text_column("id", primary_key=True),
        text_column("document_id", sa.ForeignKey("documents.id"), nullable=False),
        text_column("description", nullable=False),
        text_column("scope", nullable=False, server_default="full"),
        text_column("created_at", nullable=False),
        sa.Column("target_page", sa.Integer),
    )
    op.create_table(
        "versions",
        text_column("id", primary_key=True),
        text_column("document_id", sa.ForeignKey("documents.id"), nullable=False),
        text_column("request_id", sa.ForeignKey("change_requests.id")),
        sa.Column("version_number", sa.Integer, nullable=False),
        text_column("content", nullable=False),
        text_column("status", nullable=False, server_default="draft"),
        text_column("created_at", nullable=False),
        text_column("source_document_id", sa.ForeignKey("documents.id")),
        text_column("parent_version_id", sa.ForeignKey("versions.id")),
        sa.Column("target_page", sa.Integer),
        text_column("model"),
        text_column("prompt_version"),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("temperature", sa.Float),
        sa.Column("structured_output", sa.Integer),
        text_column("structured_json"),
        text_column("provider"),
        sa.Column("fallback_used", sa.Integer),
        text_column("fallback_reason"),
        text_column("created_by"),
        sa.UniqueConstraint("document_id", "version_number"),
    )
    op.create_table(
        "evaluations",
        text_column("id", primary_key=True),
        text_column("version_id", sa.ForeignKey("versions.id"), nullable=False),
        text_column("status", nullable=False),
        text_column("metrics_json", nullable=False),
        text_column("findings_json", nullable=False),
        text_column("evaluator_version", nullable=False),
        text_column("created_at", nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("seq", sa.Integer, primary_key=True, autoincrement=True),
        text_column("id", nullable=False, unique=True),
        text_column("ts", nullable=False),
        text_column("user", nullable=False),
        text_column("action", nullable=False),
        text_column("entity", nullable=False),
        text_column("entity_id", nullable=False),
        text_column("payload_json", nullable=False),
        text_column("prev_hash", nullable=False, unique=True),
        text_column("hash", nullable=False, unique=True),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "finding_feedback",
        text_column("id", primary_key=True),
        text_column("evaluation_id", sa.ForeignKey("evaluations.id"), nullable=False),
        sa.Column("finding_index", sa.Integer, nullable=False),
        text_column("finding_type", nullable=False),
        text_column("verdict", nullable=False),
        text_column("user", nullable=False),
        text_column("created_at", nullable=False),
        sa.CheckConstraint("verdict IN ('true_problem', 'false_alarm')"),
        sa.UniqueConstraint("evaluation_id", "finding_index", "user"),
    )
    op.create_table(
        "jobs",
        text_column("id", primary_key=True),
        text_column("kind", nullable=False),
        text_column("document_id", sa.ForeignKey("documents.id"), nullable=False),
        text_column("created_by", nullable=False),
        text_column("status", nullable=False),
        text_column("stage", nullable=False),
        sa.Column("http_status", sa.Integer),
        text_column("detail"),
        text_column("version_id"),
        text_column("result_json"),
        text_column("created_at", nullable=False),
        text_column("updated_at", nullable=False),
    )
    op.create_table(
        "users",
        text_column("id", primary_key=True),
        text_column("username", nullable=False, unique=True),
        text_column("password_hash", nullable=False),
        text_column("role", nullable=False),
        text_column("created_at", nullable=False),
    )
    op.create_table(
        "review_history",
        text_column("id", primary_key=True),
        text_column("version_id", sa.ForeignKey("versions.id"), nullable=False),
        text_column("decision", nullable=False),
        text_column("reviewer"),
        text_column("feedback"),
        text_column("created_at", nullable=False),
        text_column("evaluator_version"),
        text_column("evaluation_status"),
        text_column("source_sha256"),
        text_column("content_sha256"),
    )

    # Append-only audit log, enforced by the database.
    if op.get_bind().dialect.name == "sqlite":
        op.execute("CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events "
                   "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END")
        op.execute("CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events "
                   "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END")
    else:
        op.execute("""CREATE FUNCTION audit_events_append_only() RETURNS trigger AS $$
                      BEGIN RAISE EXCEPTION 'audit_events is append-only'; END $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events "
                   "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()")
        op.execute("CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events "
                   "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()")


def downgrade():
    raise NotImplementedError("The baseline is not reversible; restore a backup instead.")
