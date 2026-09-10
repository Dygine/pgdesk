"""
One-time sign-in keys, handed to a new resident as a QR code.

The problem this solves is typing. A temporary password like `kX7p9QmR#4` is
fine to read off a screen at a desk and miserable to type on a phone keyboard,
so a resident's first sign-in is where onboarding stalls. The PG shows a QR
instead; the resident scans it on the login screen and is signed in, then sets
a password of their own.

Why the QR carries a key and not the password
---------------------------------------------
The obvious design puts the email and temporary password in the QR. It cannot
honour the one rule the owner asked for - "valid for 30 minutes" - because a
password works until it is changed. A photo of that QR forwarded on WhatsApp is
the resident's password, indefinitely.

A key can expire and can be spent. So the symbol holds a random 192-bit value,
stored here only as a SHA-256 digest (the same treatment refresh tokens get: a
database dump contains nothing replayable). It dies at the first of:

  - being used once
  - thirty minutes passing
  - a newer key being issued for the same resident
  - the resident choosing their own password
  - staff turning portal access off

The temporary password still exists alongside it, for the browser at a desk.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TenantMixin, Timestamps, UUIDPrimaryKey


class LoginCode(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "login_codes"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True)

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: Spent. Set under a row lock, so two phones scanning the same code at the
    #: same moment cannot both get a session.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Retired before use - replaced by a newer code, or access was withdrawn.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    #: Where it was redeemed from. Kept so "I never scanned that" is answerable.
    used_ip: Mapped[str | None] = mapped_column(String(64))
    used_user_agent: Mapped[str | None] = mapped_column(String(300))

    @property
    def is_live(self) -> bool:
        return (self.used_at is None and self.revoked_at is None
                and self.expires_at > datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<LoginCode customer={self.customer_id}>"
