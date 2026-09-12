"""
Forgotten passwords.

Three steps, three endpoints, and the split is what makes it safe:

  request   an address goes in, a code goes out by email. Answers identically
            whether or not the address exists.
  verify    the code is checked and exchanged for a short-lived token.
  reset     the token is spent and a new password is set.

The address is only supplied in step one. Steps two and three carry the token,
and step three reads the address back out of it - so a caller cannot verify one
address and then reset another's password. That is the single most important
property here and the reason this is not one endpoint taking email, code and
password together.

Staff and residents share the flow. They are separate tables with separate
logins, so an address is looked up in both; if it somehow exists in each, the
staff account wins, because that is the account whose compromise costs more and
the person will notice a reset they did not ask for.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import hash_password
from app.models import Customer, User
from app.models.otp import OtpPurpose
from app.models.enums import PrincipalKind
from app.services.auth_service import AuthService, Principal
from app.services.email_service import (
    EmailNotConfigured, EmailSendFailed, EmailService,
)
from app.services.otp_service import OtpService, normalise_email
from app.services.platform_settings_service import PlatformSettingsService

log = logging.getLogger("pgguru.password_reset")

#: Said to everyone, whether or not the address is known. Deliberately phrased
#: as a condition rather than a claim - "we sent you an email" would be a lie
#: for an address with no account, and users notice.
NEUTRAL_REPLY = ("If that email address has an account, a code is on its way. "
                 "It expires in 10 minutes.")


class PasswordResetService:
    def __init__(self, db: Session):
        self.db = db
        self.otp = OtpService(db)
        self.mail = EmailService(db)

    def _find_principal(self, email: str):
        """Staff first, then residents. Returns the row or None."""
        address = normalise_email(email)
        user = self.db.scalars(select(User).where(
            User.email == address)).first()
        if user is not None:
            return user
        return self.db.scalars(select(Customer).where(
            Customer.email == address)).first()

    # ------------------------------------------------------------- step one
    def request_code(self, email: str, *, ip: str | None = None) -> None:
        """
        Issue and mail a code. Returns nothing, and reveals nothing.

        Note the order: the code is issued *before* the account lookup decides
        anything, so the rate limiter sees every request including those for
        addresses with no account. Checking the account first would make the
        endpoint answer faster for unknown addresses, and a timing difference is
        an enumeration oracle just as surely as a different message is.
        """
        address = normalise_email(email)
        if not address or "@" not in address:
            raise ConflictError("Enter a valid email address.")

        # Raises on rate limits, which is intentional and not an enumeration
        # leak: the limit is keyed on the address the caller supplied, so it
        # tells them only about their own behaviour.
        code = self.otp.issue(
            email=address, purpose=OtpPurpose.PASSWORD_RESET, ip=ip)

        principal = self._find_principal(address)
        if principal is None:
            log.info("password reset requested for an unknown address")
            return

        if getattr(principal, "is_active", True) is False:
            # A deactivated account gets no code. Silently, for the same reason.
            log.info("password reset requested for a deactivated account")
            return

        platform = PlatformSettingsService(self.db).get()
        try:
            self.mail.send_otp(
                to=address, code=code, purpose_label="resetting your password",
                minutes=10, platform_name=platform.platform_name or "PGuru")
        except EmailNotConfigured:
            # Worth a loud log: an operator who has not configured SMTP has a
            # reset flow that silently does nothing, and nobody will report it
            # because the screen says the same thing it always says.
            log.error("password reset could not be emailed: no SMTP configured")
        except EmailSendFailed as exc:
            log.error("password reset email failed: %s", exc)

    # ------------------------------------------------------------- step two
    def verify_code(self, *, email: str, code: str) -> str:
        return self.otp.verify(
            email=email, purpose=OtpPurpose.PASSWORD_RESET, code=code)

    # ----------------------------------------------------------- step three
    def reset(self, *, token: str, new_password: str) -> str:
        """
        Spend the token, set the password, and end every existing session.

        Signing other sessions out is the part people forget. Someone resetting
        a password usually believes their account is compromised; leaving the
        attacker's session alive means the reset achieved nothing.
        """
        # Length is enforced by the request schema (min 8), which is the same
        # rule /auth/change-password applies. Repeating it here would be a
        # second place to forget to update.
        email = self.otp.consume(token=token, purpose=OtpPurpose.PASSWORD_RESET)
        principal = self._find_principal(email)
        if principal is None:
            # The account vanished between the code being verified and spent.
            # Vanishingly rare, and the token is already consumed by now, so the
            # only safe answer is to make them start over.
            raise AuthenticationError("That account is no longer available.")

        principal.password_hash = hash_password(new_password)
        if hasattr(principal, "must_change_password"):
            principal.must_change_password = False

        # Every existing session dies. Someone resetting a password usually
        # believes their account is compromised, and leaving the attacker's
        # session alive would mean the reset achieved nothing.
        is_user = isinstance(principal, User)
        AuthService(self.db).revoke_all_sessions(Principal(
            kind=PrincipalKind.USER if is_user else PrincipalKind.CUSTOMER,
            id=principal.id, email=principal.email,
            name=getattr(principal, "name", None) or getattr(principal, "full_name", ""),
            organization_id=principal.organization_id, obj=principal))
        self.db.flush()
        return email
