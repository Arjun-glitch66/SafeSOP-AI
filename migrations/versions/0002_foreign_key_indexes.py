"""Indexes on foreign keys and on the columns the list endpoints filter and sort by.

Revision ID: 0002_fk_indexes
Revises: 0001_baseline
Create Date: 2026-10-30
"""
from alembic import op

revision = "0002_fk_indexes"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_change_requests_document_id", "change_requests", ["document_id"]),
    ("ix_versions_document_id", "versions", ["document_id"]),
    ("ix_versions_request_id", "versions", ["request_id"]),
    ("ix_versions_source_document_id", "versions", ["source_document_id"]),
    ("ix_versions_parent_version_id", "versions", ["parent_version_id"]),
    ("ix_evaluations_version_id_created_at", "evaluations", ["version_id", "created_at"]),
    ("ix_review_history_version_id", "review_history", ["version_id"]),
    ("ix_finding_feedback_evaluation_id", "finding_feedback", ["evaluation_id"]),
    ("ix_jobs_document_id", "jobs", ["document_id"]),
    ("ix_jobs_created_by_created_at", "jobs", ["created_by", "created_at"]),
    ("ix_audit_events_entity", "audit_events", ["entity", "entity_id"]),
    ("ix_documents_created_at", "documents", ["created_at"]),
]


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _ in INDEXES:
        op.drop_index(name, table_name=table)
