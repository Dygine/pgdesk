"""gate QR and resident self check-in geofence

Adds the branch-side gate identity (`gate_qr_token`) and its geofence
(`latitude`, `longitude`, `geofence_radius_m`, `self_checkin_enabled`), plus the
position columns the gate log keeps for every self check-in.

Every column is nullable or carries a server default, so this migration is safe
to apply to a populated database while the previous release is still serving:
existing branches simply have self check-in switched off until an owner
positions them.

Revision ID: 0008_gate_geofence
Revises: 0007_login_attempts
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = '0008_gate_geofence'
down_revision: str | None = '0007_login_attempts'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----------------------------------------------------------- branches
    op.add_column("branches", sa.Column("gate_qr_token", sa.String(length=64), nullable=True))
    op.add_column("branches", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("branches", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("branches", sa.Column(
        "geofence_radius_m", sa.Integer(), nullable=False, server_default="150"))
    op.add_column("branches", sa.Column(
        "self_checkin_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))

    # Unique because the token is the sole lookup key for "which gate is this",
    # and indexed because that lookup happens on every resident scan.
    op.create_index("ix_branches_gate_qr_token", "branches", ["gate_qr_token"], unique=True)

    # A radius of zero would make the gate unreachable and a radius of tens of
    # kilometres would make the geofence meaningless. Bounded in the database as
    # well as the schema, because the schema only guards the one path that uses it.
    op.create_check_constraint(
        "ck_branches_geofence_radius", "branches",
        "geofence_radius_m >= 10 AND geofence_radius_m <= 5000")
    op.create_check_constraint(
        "ck_branches_latitude", "branches",
        "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)")
    op.create_check_constraint(
        "ck_branches_longitude", "branches",
        "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)")

    # ---------------------------------------------------------- gate_logs
    op.add_column("gate_logs", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("gate_logs", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("gate_logs", sa.Column("accuracy_m", sa.Float(), nullable=True))
    op.add_column("gate_logs", sa.Column("distance_m", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("gate_logs", "distance_m")
    op.drop_column("gate_logs", "accuracy_m")
    op.drop_column("gate_logs", "longitude")
    op.drop_column("gate_logs", "latitude")

    op.drop_constraint("ck_branches_longitude", "branches", type_="check")
    op.drop_constraint("ck_branches_latitude", "branches", type_="check")
    op.drop_constraint("ck_branches_geofence_radius", "branches", type_="check")
    op.drop_index("ix_branches_gate_qr_token", table_name="branches")

    op.drop_column("branches", "self_checkin_enabled")
    op.drop_column("branches", "geofence_radius_m")
    op.drop_column("branches", "longitude")
    op.drop_column("branches", "latitude")
    op.drop_column("branches", "gate_qr_token")
