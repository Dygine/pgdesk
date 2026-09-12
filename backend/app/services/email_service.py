"""
Sending email.

Until now nothing in PGuru sent a message anywhere - the notification service
wrote rows to a table and the settings screen honestly reported email as "not
configured". This is the part that actually delivers.

Two sources of configuration, checked in this order:

  1. The environment (SMTP_HOST, SMTP_PORT, ...). Wins when present, so a
     deployment already configured this way keeps behaving identically and an
     operator cannot lock themselves out of mail by saving a bad form.
  2. `platform_settings`, written by a master admin, password encrypted at rest.

Delivery is synchronous and inside the request. That is a deliberate limit, not
an oversight: there is no queue or worker in this codebase, and inventing one
for a feature that sends a handful of messages a day would be the larger
mistake. It does mean a slow mail server makes a request slow, so the socket
timeout is short and every caller treats failure as non-fatal - a password reset
whose email fails must still not tell the caller whether the address exists.
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
from urllib import error as urlerror, request as urlrequest
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy.orm import Session

from app.core.crypto import decrypt
from app.models import PlatformSettings
from app.models.platform import SINGLETON_ID

log = logging.getLogger("pgguru.email")

#: Long enough for a slow relay, short enough that a dead host does not hold a
#: web worker open. A user waiting 10 seconds for "check your email" is already
#: a bad experience; 30 would be an outage.
SMTP_TIMEOUT_SECONDS = 10

#: Brevo's transactional send endpoint.
BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


class EmailNotConfigured(Exception):
    """No usable SMTP configuration. Distinct from a send that was attempted."""


class EmailSendFailed(Exception):
    """The server was reachable and refused, or the connection broke."""


@dataclass(frozen=True)
class BrevoConfig:
    """
    Brevo's transactional API.

    No host or port here, and that is the entire point: this posts to
    https://api.brevo.com over 443, the same port every other outbound request
    already uses. SMTP ports are blocked on a lot of managed hosting; 443 is
    blocked nowhere, because blocking it would break the platform itself.
    """

    api_key: str
    from_email: str
    from_name: str
    source: str

    kind: str = "brevo"


@dataclass(frozen=True)
class MailConfig:
    host: str
    port: int
    username: str | None
    password: str | None
    from_email: str
    from_name: str
    use_tls: bool
    use_ssl: bool
    source: str          # "environment" or "platform settings"

    kind: str = "smtp"


def _from_environment() -> MailConfig | None:
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM")
    if not (host and sender):
        return None
    return MailConfig(
        host=host,
        port=int(os.getenv("SMTP_PORT") or 587),
        username=os.getenv("SMTP_USERNAME") or None,
        password=os.getenv("SMTP_PASSWORD") or None,
        from_email=sender,
        from_name=os.getenv("SMTP_FROM_NAME") or "PGuru",
        use_tls=(os.getenv("SMTP_USE_TLS", "true").lower() != "false"),
        use_ssl=(os.getenv("SMTP_USE_SSL", "false").lower() == "true"),
        source="environment",
    )


def _from_database(db: Session) -> MailConfig | None:
    import uuid

    row = db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
    if row is None or not row.smtp_host or not row.smtp_from_email:
        return None
    return MailConfig(
        host=row.smtp_host,
        port=row.smtp_port or 587,
        username=row.smtp_username or None,
        password=decrypt(row.smtp_password_encrypted),
        from_email=row.smtp_from_email,
        from_name=row.smtp_from_name or (row.platform_name or "PGuru"),
        use_tls=bool(row.smtp_use_tls),
        use_ssl=bool(row.smtp_use_ssl),
        source="platform settings",
    )


def _brevo_from_environment() -> BrevoConfig | None:
    key = os.getenv("BREVO_API_KEY")
    sender = os.getenv("BREVO_SENDER_EMAIL")
    if not (key and sender):
        return None
    return BrevoConfig(api_key=key, from_email=sender,
                       from_name=os.getenv("BREVO_SENDER_NAME") or "PGuru",
                       source="environment")


def _brevo_from_database(db: Session) -> BrevoConfig | None:
    import uuid

    row = db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
    if row is None or not row.brevo_sender_email:
        return None
    key = decrypt(row.brevo_api_key_encrypted)
    if not key:
        return None
    return BrevoConfig(
        api_key=key, from_email=row.brevo_sender_email,
        from_name=row.brevo_sender_name or (row.platform_name or "PGuru"),
        source="platform settings")


def selected_provider(db: Session) -> str:
    """Which transport the operator chose. Defaults to SMTP."""
    import uuid

    row = db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
    return (row.email_provider if row and row.email_provider else "smtp")


def resolve_config(db: Session) -> MailConfig | BrevoConfig | None:
    """
    The transport that will actually be used.

    Environment beats database for both, so a deployment already configured
    that way keeps behaving identically and an operator cannot lock themselves
    out of mail by saving a bad form.
    """
    if selected_provider(db) == "brevo":
        return _brevo_from_environment() or _brevo_from_database(db)
    return _from_environment() or _from_database(db)


def is_configured(db: Session) -> bool:
    return resolve_config(db) is not None


class EmailService:
    def __init__(self, db: Session):
        self.db = db

    def send(self, *, to: str, subject: str, body: str,
             html: str | None = None) -> None:
        """
        Deliver one message, or raise.

        Raises rather than returning a boolean because the two failure modes need
        different handling by different callers: a master admin pressing "send
        test email" wants the SMTP error verbatim, while a password reset wants
        to log it and say nothing. A bool would flatten that.
        """
        config = resolve_config(self.db)
        if config is None:
            raise EmailNotConfigured(
                "No mail provider is configured. A master admin can set one "
                "under Platform settings, or it can be supplied in the "
                "environment.")

        if config.kind == "brevo":
            self._send_brevo(config, to=to, subject=subject, body=body, html=html)
            return

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((config.from_name, config.from_email))
        message["To"] = to
        message.set_content(body)
        if html:
            message.add_alternative(html, subtype="html")

        try:
            if config.use_ssl:
                # Implicit TLS, normally port 465: the socket is encrypted before
                # any SMTP conversation happens.
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(config.host, config.port,
                                      timeout=SMTP_TIMEOUT_SECONDS,
                                      context=context) as smtp:
                    self._deliver(smtp, config, message)
            else:
                with smtplib.SMTP(config.host, config.port,
                                  timeout=SMTP_TIMEOUT_SECONDS) as smtp:
                    if config.use_tls:
                        smtp.starttls(context=ssl.create_default_context())
                    self._deliver(smtp, config, message)
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailSendFailed(
                "The mail server rejected the username or password. If this is "
                "Gmail, an ordinary account password will not work - it needs an "
                f"app password. ({exc.smtp_code})") from exc
        except smtplib.SMTPException as exc:
            raise EmailSendFailed(f"The mail server refused the message: {exc}") from exc
        except (OSError, ssl.SSLError) as exc:
            # Wrong port, wrong host, firewall, TLS on a plaintext port. All of
            # these arrive as socket errors and all of them mean the same thing
            # to an operator: the connection details are wrong.
            raise EmailSendFailed(
                f"Could not reach {config.host}:{config.port}. Check the host, "
                f"the port, and whether TLS should be on. ({exc})") from exc

    @staticmethod
    def _send_brevo(config: BrevoConfig, *, to: str, subject: str,
                    body: str, html: str | None) -> None:
        """
        POST the message to Brevo's transactional endpoint.

        Uses urllib rather than a HTTP client library on purpose. This is one
        JSON POST to one URL, and `httpx` is currently declared as a test
        dependency - reaching for it here would quietly make the whole test
        stack a production requirement. The standard library is enough.
        """
        payload = {
            "sender": {"name": config.from_name, "email": config.from_email},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        }
        if html:
            payload["htmlContent"] = html

        request = urlrequest.Request(
            BREVO_ENDPOINT,
            data=json.dumps(payload).encode(),
            headers={
                "api-key": config.api_key,
                "content-type": "application/json",
                "accept": "application/json",
            },
            method="POST",
        )

        try:
            with urlrequest.urlopen(request, timeout=SMTP_TIMEOUT_SECONDS) as res:
                if res.status not in (200, 201, 202):
                    raise EmailSendFailed(f"Brevo returned {res.status}.")
        except urlerror.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode()).get("message", "")
            except Exception:                                   # noqa: BLE001
                pass
            if exc.code == 401:
                raise EmailSendFailed(
                    "Brevo rejected the API key. Check it has not been deleted "
                    "or expired in the Brevo dashboard.") from exc
            if exc.code == 400 and "sender" in detail.lower():
                # By far the most common Brevo failure, and the message it
                # returns on its own does not say what to do about it.
                raise EmailSendFailed(
                    f"Brevo refused the sender address {config.from_email}. It "
                    "must be verified under Senders, domains, IPs in Brevo "
                    f"before it can send. ({detail})") from exc
            raise EmailSendFailed(
                f"Brevo refused the message: {detail or exc.code}") from exc
        except urlerror.URLError as exc:
            raise EmailSendFailed(
                f"Could not reach Brevo: {exc.reason}") from exc

    @staticmethod
    def _deliver(smtp, config: MailConfig, message: EmailMessage) -> None:
        if config.username and config.password:
            smtp.login(config.username, config.password)
        smtp.send_message(message)

    # ------------------------------------------------------------ templates
    def send_otp(self, *, to: str, code: str, purpose_label: str,
                 minutes: int, platform_name: str = "PGuru") -> None:
        """
        The one-time code mail.

        The code is in the subject line as well as the body. On a phone the
        notification preview is often all anyone reads, and putting it there
        saves opening the message at all - which is also why the subject says
        what the code is for: a bare number in a banner is indistinguishable
        from a code someone else requested for an attack in progress.
        """
        subject = f"{code} is your {platform_name} verification code"
        body = (
            f"Your {platform_name} verification code is:\n\n"
            f"    {code}\n\n"
            f"It is for {purpose_label} and expires in {minutes} minutes.\n\n"
            "If you did not ask for this, you can ignore this email - nothing "
            "has changed on your account, and whoever requested it does not "
            "have access to it.\n\n"
            "Never share this code. Nobody from support will ask you for it.\n"
        )
        html = f"""\
<div style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
            max-width:480px;margin:0 auto;color:#0F172A">
  <h2 style="font-size:18px;margin:0 0 16px">{platform_name} verification code</h2>
  <p style="margin:0 0 20px;color:#475569;font-size:14px">
    Use this code for {purpose_label}. It expires in {minutes} minutes.</p>
  <div style="font-size:34px;font-weight:700;letter-spacing:9px;
              background:#F1F5F9;border-radius:10px;padding:18px;text-align:center">
    {code}</div>
  <p style="margin:22px 0 0;color:#64748B;font-size:13px;line-height:1.6">
    If you did not ask for this you can ignore this email. Nothing has changed
    on your account.<br>
    Never share this code — nobody from support will ask you for it.</p>
</div>"""
        self.send(to=to, subject=subject, body=body, html=html)
