"""
Refresh tokens and password-reset tokens.

Both are stored as SHA-256 digests, never as the value handed to the client. A
database dump therefore does not contain anything that can be replayed - the
same reasoning as password hashing, applied to bearer secrets.

Refresh tokens are persisted specifically so they can be revoked. A stateless
refresh token cannot be withdrawn before it expires, which makes logout a
suggestion rather than an action.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, false,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import Timestamps, UUIDPrimaryKey


class RefreshToken(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "refresh_tokens"

    # Exactly one of these is set - staff or resident. The CHECK enforces it.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Set when this token was rotated out, so a replay of the old one is detectable.
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))

    #: One device's chain of tokens.
    #:
    #: A login mints a family id; every rotation of that token inherits it. So
    #: the phone's tokens and the laptop's tokens are different families for the
    #: same person.
    #:
    #: This exists because of what reuse detection has to do when it fires. A
    #: replayed token means either a retry or a theft, and the safe answer is to
    #: revoke - but revoking *every* session for the account meant one bad
    #: refresh on a laptop signed out every installed app as well. During a
    #: deploy, when a rotation commits and its reply is lost, that is not an
    #: attack; it is a Tuesday. Revoking the family instead confines the damage
    #: to the device it happened on, which is the only device that could
    #: possibly have leaked anything.
    #:
    #: Null on rows written before this column existed. Those are treated as a
    #: family of one, which is the conservative reading.
    family_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)

    #: Whether this chain belongs to an installed app rather than a browser.
    #: Recorded on the row so a rotation cannot silently downgrade a permanent
    #: app session to a 24-hour browser one because a header went missing.
    is_native: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false())

    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip_address: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND customer_id IS NULL) "
            "OR (user_id IS NULL AND customer_id IS NOT NULL)",
            name="ck_refresh_tokens_one_principal",
        ),
        Index("ix_refresh_tokens_lookup", "token_hash", "revoked_at"),
        Index("ix_refresh_tokens_family", "family_id", "revoked_at"),
    )

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at > datetime.now(timezone.utc)


class PasswordResetToken(Base, UUIDPrimaryKey, Timestamps):
    """
    Foundation only - no endpoint issues these yet, and no email is sent.

    The shape matters now because the obvious wrong design (a "reset by user id"
    endpoint) is very easy to add later under time pressure. A single-use,
    expiring, hashed token with no user id in it forecloses that.
    """

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_ip: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND customer_id IS NULL) "
            "OR (user_id IS NULL AND customer_id IS NOT NULL)",
            name="ck_password_reset_one_principal",
        ),
    )

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and self.expires_at > datetime.now(timezone.utc)
