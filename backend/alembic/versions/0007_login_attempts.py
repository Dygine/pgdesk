"""login attempt throttling

Adds the table behind brute-force protection and failed-login auditing.

Revision ID: 0007_login_attempts
Revises: 0006_platform_settings
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = '0007_login_attempts'
down_revision: str | None = '0006_platform_settings'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("successful", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_attempts_identifier", "login_attempts", ["identifier"])
    op.create_index("ix_login_attempts_ip_address", "login_attempts", ["ip_address"])
    # The lockout query is "failures for this identifier since T", so the index
    # has to cover both columns or every login does a sequential scan.
    op.create_index("ix_login_attempts_identifier_time", "login_attempts",
                    ["identifier", "created_at"])
    op.create_index("ix_login_attempts_ip_time", "login_attempts",
                    ["ip_address", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_login_attempts_ip_time", table_name="login_attempts")
    op.drop_index("ix_login_attempts_identifier_time", table_name="login_attempts")
    op.drop_index("ix_login_attempts_ip_address", table_name="login_attempts")
    op.drop_index("ix_login_attempts_identifier", table_name="login_attempts")
    op.drop_table("login_attempts")
