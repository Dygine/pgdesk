"""Scanned ID documents, up to three per resident, 5 KB each

Revision ID: 0014_resident_documents
Revises: 0013_staff_notice_menu_pay

Closes the "KYC files not stored" gap for small scans. The size cap is enforced
here as well as in the API: a CHECK on the declared size and another on the
actual byte length, so nothing over 5,120 bytes can be stored by any route.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_resident_documents"
down_revision: str | None = "0013_staff_notice_menu_pay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
MAX_BYTES = 5 * 1024


def upgrade() -> None:
    op.create_table(
        "resident_documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID,
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resident_id", UUID,
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_type", sa.String(20), nullable=False),
        sa.Column("label", sa.String(60)),
        sa.Column("mime_type", sa.String(20), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("uploaded_by_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"size_bytes > 0 AND size_bytes <= {MAX_BYTES}",
                           name="ck_resident_documents_size"),
        sa.CheckConstraint(f"octet_length(content) <= {MAX_BYTES}",
                           name="ck_resident_documents_content_size"),
        sa.CheckConstraint(
            "doc_type IN ('AADHAAR', 'PAN', 'PASSPORT', 'DRIVING_LICENCE', 'VOTER_ID', 'OTHER')",
            name="ck_resident_documents_doc_type"),
    )
    op.create_index("ix_resident_documents_organization_id", "resident_documents",
                    ["organization_id"])
    op.create_index("ix_resident_documents_resident_id", "resident_documents", ["resident_id"])


def downgrade() -> None:
    op.drop_table("resident_documents")
