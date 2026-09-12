"""Listing photos, and refresh-token families

Revision ID: 0015_photos_and_families
Revises: 0014_resident_documents

Two unrelated changes in one revision because they ship together.

1. `branch_photos` - up to six photos on a public listing, 5 KB each, same
   storage reasoning as resident_documents: no persistent disk on the API host,
   and at this size PostgreSQL does not notice. The cap is a CHECK on the
   declared size and another on the actual byte length, so nothing over 5,120
   bytes can be stored by any route, including a future one nobody has written
   yet.

2. `refresh_tokens.family_id` and `.is_native` - one device's chain of tokens,
   and whether that chain belongs to an installed app. Reuse detection used to
   revoke every session for an account, so one ambiguous refresh on a laptop
   signed out every phone. It now revokes the family, which is the device that
   actually presented the token.

   Existing rows get a family of their own rather than NULL, so the day this
   deploys nobody is left in the migration-window path. `is_native` defaults to
   false: a browser session that is really an app session will be marked native
   again on its next rotation, and the worst case in the meantime is a session
   that lasts 24 hours instead of forever.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_photos_and_families"
down_revision: str | None = "0014_resident_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
MAX_BYTES = 5 * 1024


def upgrade() -> None:
    # ------------------------------------------------------ listing photos
    op.create_table(
        "branch_photos",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID,
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", UUID,
                  sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("caption", sa.String(80)),
        sa.Column("mime_type", sa.String(20), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("source", sa.String(10), nullable=False, server_default="camera"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"size_bytes > 0 AND size_bytes <= {MAX_BYTES}",
                           name="ck_branch_photos_size"),
        sa.CheckConstraint(f"octet_length(content) <= {MAX_BYTES}",
                           name="ck_branch_photos_content_size"),
        sa.CheckConstraint("position >= 0", name="ck_branch_photos_position"),
    )
    op.create_index("ix_branch_photos_organization_id", "branch_photos", ["organization_id"])
    op.create_index("ix_branch_photos_branch_id", "branch_photos", ["branch_id"])
    # The seeker's search reads photos branch by branch, newest listing first.
    op.create_index("ix_branch_photos_branch_position", "branch_photos",
                    ["branch_id", "position"])

    # ------------------------------------------------------ token families
    op.add_column("refresh_tokens", sa.Column("family_id", UUID, nullable=True))
    op.add_column("refresh_tokens",
                  sa.Column("is_native", sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    # Give every live token its own family. A row whose family is itself is a
    # chain of one, which is exactly what an un-rotated login is.
    op.execute("UPDATE refresh_tokens SET family_id = id WHERE family_id IS NULL")
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_family", "refresh_tokens",
                    ["family_id", "revoked_at"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_family", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "is_native")
    op.drop_column("refresh_tokens", "family_id")
    op.drop_table("branch_photos")
