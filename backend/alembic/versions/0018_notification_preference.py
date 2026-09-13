"""Per-person notification preference

Revision ID: 0018_notification_preference
Revises: 0017_push_notifications

One switch per person, on both principal tables, so an owner, a warden and a
resident all get the same control in the same place.

Defaults to true. The alternative - default off, let people opt in - sounds
more polite and is worse: an invoice notification that never arrives because
nobody found a setting is indistinguishable from a broken feature, and the
person who wanted it never learns it exists. They can turn it off in one tap
from their own profile, which is the part that actually matters.

Deliberately NOT stored on `device_tokens`. The preference belongs to the
person, not the handset: someone who turns notifications off and then installs
the app on a new phone has not changed their mind.
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0018_notification_preference"
down_revision: str | None = "0017_push_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("users", "customers"):
        op.add_column(
            table,
            sa.Column("notifications_enabled", sa.Boolean(), nullable=False,
                      server_default=sa.true()))


def downgrade() -> None:
    for table in ("users", "customers"):
        op.drop_column(table, "notifications_enabled")
