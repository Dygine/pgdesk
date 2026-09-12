"""
People looking for a PG, with an account of their own.

The first version of the public side had no seeker account at all: a verified
email, one enquiry, and the verification was spent. Sending a second enquiry
meant a second emailed code, a third meant a third. Nobody shortlisting four
PGs on a Sunday does that.

So a seeker now signs up once - name, phone, and an email proved by a code -
and gets a session they keep on their phone. With it they can enquire at any
number of PGs in one tap and see what happened to each enquiry.

Why this is NOT a third kind of principal
-----------------------------------------
Every login in the system (`users`, `customers`) belongs to an organisation,
and the whole tenant isolation model - CurrentScope, the 404-not-403 rule, the
refresh-token table's one-principal CHECK - is built on that. A seeker belongs
to no organisation. Threading them through all of it would put the one
guarantee that must never slip within reach of the least trusted account type.

Instead a seeker session is a separate, deliberately weak credential:

  - its own table and its own header (`X-PGuru-Seeker`), never `Authorization`
  - accepted only by `/public/seeker/*`; nothing else in the API reads it
  - it can do exactly three things: read listings, send enquiries, and read the
    seeker's own enquiries back

A leaked seeker token lets someone send enquiries in that person's name. That
is the whole blast radius, which is why it can live in ordinary app storage.

The seeker table is not tenant data. Enquiries are - each one belongs to the PG
that received it - and they are matched back to the seeker by the verified
email, which also picks up enquiries sent before the account existed.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, true
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import Timestamps, UUIDPrimaryKey


class PgSeeker(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "pg_seekers"

    #: Lower-cased, and proved by an emailed code before the row exists.
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["SeekerSession"]] = relationship(
        back_populates="seeker", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<PgSeeker {self.email}>"


class SeekerSession(Base, UUIDPrimaryKey, Timestamps):
    """An opaque token, stored as a digest, like every other bearer secret here."""

    __tablename__ = "seeker_sessions"

    seeker_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("pg_seekers.id", ondelete="CASCADE"),
        nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip_address: Mapped[str | None] = mapped_column(String(64))

    seeker: Mapped[PgSeeker] = relationship(back_populates="sessions")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > datetime.now(timezone.utc)
