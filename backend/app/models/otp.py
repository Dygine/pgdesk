"""
One-time codes sent to an email address.

Two callers today - forgotten passwords, and verifying an address during signup -
and they share a table because they share every property that matters: short
lived, single use, rate limited, and bounded in how many times a code may be
guessed.

Why not reuse `password_reset_tokens`. That table holds a long random token that
travels in a link, and it is keyed to a principal that already exists. A code
typed by a human is a different object: six digits are guessable, so the number
of attempts has to be counted and capped, and signup needs a code for an address
that has no account behind it yet. Bending one table to do both would mean a
nullable principal on the reset table and an attempt counter that only one path
uses.

The code is stored as a hash. Six digits is a small space, but a database dump
containing live plaintext codes for every pending reset is still worth avoiding,
and hashing costs nothing here.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import Timestamps, UUIDPrimaryKey


class OtpPurpose:
    """Not an enum column: the set is small and stable, and a CHECK is enough."""

    PASSWORD_RESET = "PASSWORD_RESET"
    SIGNUP_EMAIL = "SIGNUP_EMAIL"

    ALL = (PASSWORD_RESET, SIGNUP_EMAIL)


class OtpCode(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "otp_codes"

    purpose: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    #: Lower-cased. The address is the subject here, not a foreign key: a signup
    #: code is issued before any row exists to point at, and a reset code must
    #: not reveal whether one does.
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Set when a code is verified, and cleared when it is spent. This is what a
    #: client presents to /reset-password, so that the new password and the code
    #: never travel in the same request - a code proved once should not have to
    #: be held by the client and replayed.
    verification_token_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    requested_ip: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint(
            "purpose IN ('PASSWORD_RESET', 'SIGNUP_EMAIL')",
            name="ck_otp_codes_purpose"),
        CheckConstraint("max_attempts BETWEEN 1 AND 20", name="ck_otp_codes_max_attempts"),
        # Issuing is throttled by counting recent rows for an address, so that
        # query must not be a sequential scan on a table nobody ever prunes.
        Index("ix_otp_codes_email_purpose_time", "email", "purpose", "created_at"),
    )

    @property
    def is_live(self) -> bool:
        """Still usable: not spent, not expired, attempts remaining."""
        return (self.consumed_at is None
                and self.attempts < self.max_attempts
                and self.expires_at > datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<OtpCode {self.purpose} {self.email}>"
