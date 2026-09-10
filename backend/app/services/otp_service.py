"""
Emailed one-time codes.

Used by forgotten passwords today and by signup email verification next. The
whole point of this module is that a six-digit code is a weak secret, and every
protection here exists because of that.

Six digits is one in a million per guess. That is fine when guessing is
expensive and useless when it is free, so three separate limits apply:

  Per code      five wrong attempts and the code is dead. An attacker gets five
                tries out of a million, not a million.
  Per address   a handful of codes per hour, so an attacker cannot simply
                request ten thousand codes and try one guess against each.
  Per address   a short cooldown between sends, which also stops the endpoint
                being used to mail-bomb someone.

The last two matter more than they look. Capping guesses per code without
capping how many codes may be issued moves the attack rather than stopping it.

Enumeration
-----------
`/forgot-password` answers identically whether or not the address exists. If it
did not, it would be a free tool for discovering which residents and staff have
accounts, and every user list is worth money to somebody. The cost is that a
person who mistypes their address waits for a mail that never comes - which is
why the response says "if that address has an account" rather than "sent".
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import OtpCode
from app.models.otp import OtpPurpose

log = logging.getLogger("pgdesk.otp")

CODE_LENGTH = 6
CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5

#: Codes per address per window, and the pause between two sends.
MAX_SENDS_PER_HOUR = 5
RESEND_COOLDOWN_SECONDS = 60

#: How long a verified code stays spendable. Short, because by this point the
#: user is on the "choose a password" screen with the token already in hand -
#: fifteen minutes is generous for typing a password and stops a token left in
#: a closed tab being useful an hour later.
VERIFIED_TTL_MINUTES = 15


class OtpError(Exception):
    """A refusal the caller should show, with a machine-readable code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _generate_code() -> str:
    """
    Uniformly distributed six digits, leading zeros allowed.

    `secrets.randbelow` rather than `random`: the latter is seeded predictably
    and its output is reconstructable from a handful of samples, which for a
    password-reset code would be the whole ballgame.
    """
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


class OtpService:
    def __init__(self, db: Session):
        self.db = db

    # --------------------------------------------------------------- issue
    def issue(self, *, email: str, purpose: str, ip: str | None = None) -> str:
        """
        Create a code and return it in plaintext, once, for the caller to mail.

        The plaintext is never stored and never returned again. If the mail
        fails, the code is lost and the user asks for another - which is the
        correct outcome, because the alternative is a readable code sitting in a
        table.
        """
        if purpose not in OtpPurpose.ALL:
            raise ValueError(f"unknown OTP purpose {purpose!r}")

        address = normalise_email(email)
        now = datetime.now(timezone.utc)

        recent = self.db.scalar(
            select(func.count(OtpCode.id)).where(
                OtpCode.email == address, OtpCode.purpose == purpose,
                OtpCode.created_at > now - timedelta(hours=1))) or 0
        if recent >= MAX_SENDS_PER_HOUR:
            raise OtpError(
                "too_many",
                "Too many codes have been requested for this address. "
                "Please wait an hour and try again.")

        last = self.db.scalars(
            select(OtpCode).where(
                OtpCode.email == address, OtpCode.purpose == purpose)
            .order_by(OtpCode.created_at.desc()).limit(1)).first()
        if last and (now - last.created_at).total_seconds() < RESEND_COOLDOWN_SECONDS:
            wait = RESEND_COOLDOWN_SECONDS - int((now - last.created_at).total_seconds())
            raise OtpError("cooldown", f"Please wait {wait} seconds before asking again.")

        # Any earlier live code for this address is retired. Two valid codes at
        # once doubles an attacker's guesses and confuses a user who has three
        # emails open and tries the wrong one.
        for row in self.db.scalars(select(OtpCode).where(
                OtpCode.email == address, OtpCode.purpose == purpose,
                OtpCode.consumed_at.is_(None))).all():
            row.consumed_at = now

        code = _generate_code()
        self.db.add(OtpCode(
            purpose=purpose, email=address, code_hash=_hash(code),
            expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
            max_attempts=MAX_ATTEMPTS, requested_ip=ip))
        self.db.flush()
        return code

    # -------------------------------------------------------------- verify
    def verify(self, *, email: str, purpose: str, code: str) -> str:
        """
        Check a code and hand back a short-lived token proving it was checked.

        The token exists so the code and the new password never travel in the
        same request. Without it, the client has to hold the code and replay it
        alongside the password, which puts a live credential in a second place
        and makes the reset endpoint a second thing to rate limit.
        """
        address = normalise_email(email)
        now = datetime.now(timezone.utc)

        row = self.db.scalars(
            select(OtpCode).where(
                OtpCode.email == address, OtpCode.purpose == purpose,
                OtpCode.consumed_at.is_(None))
            .order_by(OtpCode.created_at.desc()).limit(1)
            # Locked because the attempt counter is read, incremented and
            # written. Two guesses arriving together would otherwise both read
            # the same count and only one increment would survive, which turns a
            # five-attempt cap into an unbounded one under concurrency.
            .with_for_update()).first()

        if row is None:
            raise OtpError("no_code", "Ask for a new code - this one is no longer valid.")
        if row.expires_at <= now:
            raise OtpError("expired", "That code has expired. Ask for a new one.")
        if row.attempts >= row.max_attempts:
            raise OtpError("locked", "Too many wrong attempts. Ask for a new code.")

        # Counted before comparing, so an attempt that crashes midway is still
        # an attempt. Counting only failures would let a client abandon requests
        # to guess for free.
        row.attempts += 1
        self.db.flush()

        if not secrets.compare_digest(row.code_hash, _hash((code or "").strip())):
            left = row.max_attempts - row.attempts
            if left <= 0:
                row.consumed_at = now
                self.db.flush()
                raise OtpError("locked", "Too many wrong attempts. Ask for a new code.")
            raise OtpError(
                "wrong", f"That code is not right. {left} "
                         f"{'attempt' if left == 1 else 'attempts'} left.")

        token = secrets.token_urlsafe(32)
        row.verification_token_hash = _hash(token)
        row.verified_at = now
        row.expires_at = now + timedelta(minutes=VERIFIED_TTL_MINUTES)
        self.db.flush()
        return token

    # --------------------------------------------------------------- spend
    def consume(self, *, token: str, purpose: str) -> str:
        """
        Spend a verification token and return the address it proved.

        Returning the email is the point: the reset endpoint never takes an
        address from the request, so a client cannot verify one address and then
        reset the password of another.
        """
        now = datetime.now(timezone.utc)
        row = self.db.scalars(
            select(OtpCode).where(
                OtpCode.verification_token_hash == _hash((token or "").strip()),
                OtpCode.purpose == purpose)
            .with_for_update()).first()

        if row is None or row.consumed_at is not None:
            raise OtpError("bad_token", "That verification has already been used. Start again.")
        if row.expires_at <= now:
            raise OtpError("expired", "That verification has expired. Start again.")

        row.consumed_at = now
        self.db.flush()
        return row.email
