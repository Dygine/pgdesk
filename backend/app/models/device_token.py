"""
One row per phone that has agreed to receive push notifications.

Why a table and not a column on the user
----------------------------------------
A person has more than one device - a phone and a tablet, or a phone they
replaced last month and never signed out of. A column would hold the last one
and silently stop delivering to the rest.

Why the token is unique across the whole table
----------------------------------------------
The token identifies the *installation*, not the person. Phones get handed on:
a resident checks out, the next resident installs the app on the same handset,
or a warden signs out and a colleague signs in. Firebase hands back the same
token in all three cases.

If the token were not unique, the old row would survive and the previous
occupant's rent reminders would arrive on somebody else's phone. So registering
a token that already exists *moves* it to the new owner rather than inserting a
second row - enforced here by the unique constraint, and relied on by
`PushService.register`.

Recipient shape
---------------
Exactly one of `user_id` / `resident_id`, mirroring `notifications`. The same
CHECK is used deliberately: the dispatcher joins these two tables on the
recipient, and two tables that disagree about what a recipient is would need a
translation layer that is only ever a place for bugs to live.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, String,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import Timestamps, UUIDPrimaryKey


class DeviceToken(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "device_tokens"

    #: Nullable, and deliberately NOT TenantMixin.
    #:
    #: A master admin has no organisation - `users` enforces that with a CHECK -
    #: and the master admin is exactly the person who has to prove push works
    #: from the settings screen. A NOT NULL column here would make the one
    #: account that needs the test button the one account unable to register a
    #: phone.
    #:
    #: This does not weaken tenant isolation: a token is only ever found through
    #: its owner (`user_id` / `resident_id`), never by organisation, so the
    #: column is provenance rather than a filter.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True)

    #: The FCM registration token. Long - Firebase does not document a maximum
    #: and current tokens run past 160 characters, so 500 is headroom rather
    #: than a guess that will need a migration.
    token: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)

    #: "android", "ios" or "web". Not an enum: the set will grow and a CHECK
    #: costs a migration to add a platform that needs no other code change.
    platform: Mapped[str] = mapped_column(String(10), nullable=False, default="android")

    #: Refreshed every time the app starts and re-registers. A token nobody has
    #: presented for months belongs to an app that was removed, and Firebase
    #: will eventually reject it; this is what makes pruning possible without
    #: waiting for that rejection.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Set when the user signs out, or when Firebase tells us the token is dead.
    #: Kept rather than deleted so "why did they stop getting notifications" is
    #: an answerable question.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(60))

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND resident_id IS NULL) "
            "OR (user_id IS NULL AND resident_id IS NOT NULL)",
            name="ck_device_tokens_one_owner"),
        CheckConstraint(
            "platform IN ('android', 'ios', 'web')",
            name="ck_device_tokens_platform"),
        # The dispatcher's hot query: every live token for one recipient.
        Index("ix_device_tokens_user_live", "user_id", "revoked_at"),
        Index("ix_device_tokens_resident_live", "resident_id", "revoked_at"),
    )

    @property
    def is_live(self) -> bool:
        return self.revoked_at is None

    def __repr__(self) -> str:
        owner = self.user_id or self.resident_id
        return f"<DeviceToken {self.platform} {owner}>"
