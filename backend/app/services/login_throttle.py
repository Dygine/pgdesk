"""
Brute-force protection for the sign-in endpoint.

Unlimited free guesses turn any weak password into a matter of time, so failures
are counted and, past a threshold, the endpoint stops answering normally.

Two counters, because they defend different attacks:

  by identifier   one account guessed repeatedly
  by IP           many accounts sprayed from one source, which the per-identifier
                  counter would never notice since no single account is hit hard

Both are sliding windows rather than fixed buckets: a fixed window lets an
attacker spend the whole budget at :59 and the whole next budget at :00.

A successful sign-in clears the identifier's failures, so a person who mistypes
their password four times and then gets it right is not locked out afterwards.

The response to a lockout is 429 with a Retry-After, and deliberately the same
whether or not the account exists - otherwise the lockout itself becomes the
enumeration oracle that the generic login failure was written to avoid.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import RateLimitedError
from app.models import LoginAttempt

#: Failures against one identifier before it is locked.
MAX_FAILURES_PER_IDENTIFIER = 5
#: Failures from one address across any identifiers before it is locked.
MAX_FAILURES_PER_IP = 20
#: How far back failures are counted, and how long a lockout lasts.
WINDOW = timedelta(minutes=15)


class LoginThrottle:
    def __init__(self, db: Session):
        self.db = db

    def _since(self) -> datetime:
        return datetime.now(timezone.utc) - WINDOW

    def _failures(self, *, identifier: str | None = None,
                  ip_address: str | None = None) -> int:
        stmt = select(func.count(LoginAttempt.id)).where(
            LoginAttempt.successful.is_(False),
            LoginAttempt.created_at >= self._since())
        if identifier:
            stmt = stmt.where(LoginAttempt.identifier == identifier)
        if ip_address:
            stmt = stmt.where(LoginAttempt.ip_address == ip_address)
        return self.db.scalar(stmt) or 0

    def check(self, identifier: str, ip_address: str | None) -> None:
        """Raise if this identifier or address has spent its budget."""
        if self._failures(identifier=identifier) >= MAX_FAILURES_PER_IDENTIFIER:
            raise RateLimitedError(
                "Too many sign-in attempts. Try again in a few minutes.",
                retry_after=int(WINDOW.total_seconds()))
        if ip_address and self._failures(ip_address=ip_address) >= MAX_FAILURES_PER_IP:
            raise RateLimitedError(
                "Too many sign-in attempts from this network. "
                "Try again in a few minutes.",
                retry_after=int(WINDOW.total_seconds()))

    def check_ip(self, ip_address: str | None) -> None:
        """
        The per-address budget alone, for sign-in paths with no identifier.

        A QR sign-in carries a random key rather than an email, so there is no
        account to count against - but a source spraying keys should still hit
        the same wall as one spraying passwords.
        """
        if ip_address and self._failures(ip_address=ip_address) >= MAX_FAILURES_PER_IP:
            raise RateLimitedError(
                "Too many sign-in attempts from this network. "
                "Try again in a few minutes.",
                retry_after=int(WINDOW.total_seconds()))

    def record(self, identifier: str, ip_address: str | None, *,
               successful: bool, reason: str | None = None) -> None:
        self.db.add(LoginAttempt(
            identifier=identifier[:255], ip_address=(ip_address or None),
            successful=successful, reason=reason))

    def clear(self, identifier: str) -> None:
        """
        Forget this identifier's failures after a correct password.

        Rows are deleted rather than left to age out so that four typos followed
        by a success do not leave someone one mistake away from a lockout for
        the rest of the window.
        """
        self.db.query(LoginAttempt).filter(
            LoginAttempt.identifier == identifier,
            LoginAttempt.successful.is_(False)).delete(synchronize_session=False)

    def purge(self, older_than: timedelta = timedelta(days=30)) -> int:
        """Housekeeping for a scheduled job; attempts are not kept forever."""
        cutoff = datetime.now(timezone.utc) - older_than
        return self.db.query(LoginAttempt).filter(
            LoginAttempt.created_at < cutoff).delete(synchronize_session=False)
