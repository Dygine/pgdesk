"""The public website, stored as editable content

Revision ID: 0016_site_content
Revises: 0015_photos_and_families

Two tables so the marketing site stops being a code change.

`site_blocks` holds one JSON body per section - hero, pricing, contact and so
on. JSON rather than a column per field, because a marketing page grows a field
every time someone has an idea, and a schema migration per idea is the friction
this exists to remove.

`site_images` holds either a link to an image hosted elsewhere or the bytes
themselves, never both - enforced by a CHECK so nothing downstream has to guess
which one wins. The byte cap is 120 KB, not the 5 KB that listing photos get:
those are thumbnails on a phone, this is a hero image on a laptop.

Both tables are deliberately NOT tenant-scoped. There is one public website and
it belongs to the platform, not to any one PG - so no organization_id, and the
endpoints are master-admin only.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_site_content"
down_revision: str | None = "0015_photos_and_families"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
IMAGE_MAX_BYTES = 120 * 1024


def upgrade() -> None:
    op.create_table(
        "site_blocks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("key", sa.String(40), nullable=False, unique=True),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_by_id", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_site_blocks_position"),
    )
    op.create_index("ix_site_blocks_key", "site_blocks", ["key"], unique=True)

    op.create_table(
        "site_images",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("slot", sa.String(60), nullable=False, unique=True),
        sa.Column("alt_text", sa.String(160), nullable=False, server_default=""),
        sa.Column("caption", sa.String(200)),
        sa.Column("url", sa.Text()),
        sa.Column("mime_type", sa.String(20)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("content", sa.LargeBinary()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(url IS NOT NULL AND content IS NULL) "
            "OR (url IS NULL AND content IS NOT NULL)",
            name="ck_site_images_one_source"),
        sa.CheckConstraint(
            f"content IS NULL OR octet_length(content) <= {IMAGE_MAX_BYTES}",
            name="ck_site_images_content_size"),
    )
    op.create_index("ix_site_images_slot", "site_images", ["slot"], unique=True)


def downgrade() -> None:
    op.drop_table("site_images")
    op.drop_table("site_blocks")
