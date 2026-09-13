"""
Push notifications to the installed app, through Firebase Cloud Messaging.

Why Firebase at all
-------------------
When the app is closed nothing of ours is running on the phone, and Android
will not let an app hold a socket open in the background to wait for us. The
one process that is always alive is Google Play Services, which keeps a single
connection to Google for the whole device. FCM is the only way into that
connection. WhatsApp and every other Android app work the same way; there is no
alternative that does not involve draining the battery and being killed anyway.

Why this module sends nothing itself
------------------------------------
Producers do not call this service. Eight services across the codebase already
write `Notification` rows - invoices, payments, complaints, gate passes,
announcements, checkout notices - and not one of them is changed by adding push.
`dispatch_pending` reads that table instead.

That is the whole design. A notification kind added next year gets push for
free, because push is attached to the table rather than to eight call sites, and
there is exactly one place to look when something is not delivered.

Credentials
-----------
FCM's HTTP v1 API authenticates with a Google service account, not the legacy
server key. The service account JSON is stored encrypted in platform settings so
an operator can rotate it from the settings screen rather than by redeploying,
with the environment taking priority when it is set - the same precedence the
mail configuration uses, and for the same reason.

Access tokens last an hour. They are cached in-process rather than re-minted per
message, because minting one is a signed round trip to Google and an
announcement to three hundred residents would otherwise make three hundred of
them.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt
from app.models import Customer, DeviceToken, Notification, PlatformSettings, User
from app.models.platform import SINGLETON_ID

log = logging.getLogger("pgguru.push")

FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

#: Give up after this many tries. A row that has failed five times is failing
#: for a reason that retrying will not fix - a malformed payload, a dead project
#: - and sweeping it for ever hides real failures behind noise.
MAX_PUSH_ATTEMPTS = 5

#: How many notifications one sweep drains. Small enough that a sweep finishes
#: quickly and a restart loses little, large enough that a 300-resident
#: announcement clears in a few ticks.
BATCH_SIZE = 100

#: Firebase replies that mean the token is dead and must never be tried again.
#: Distinguished from transient failures because the response to each is
#: opposite: retire the token, or retry it later.
DEAD_TOKEN_ERRORS = {"UNREGISTERED", "INVALID_ARGUMENT", "NOT_FOUND"}


class PushNotConfigured(Exception):
    """No Firebase credentials on this deployment. Not an error, just silence."""


class PushSendFailed(Exception):
    """Firebase rejected the request. The message is Google's, kept verbatim."""


# --------------------------------------------------------------- credentials
class _Credentials:
    """Resolved Firebase credentials plus a cached access token."""

    def __init__(self, project_id: str, service_account: dict):
        self.project_id = project_id
        self.service_account = service_account
        self._token: str | None = None
        self._expires_at: datetime = datetime.now(timezone.utc)
        self._lock = threading.Lock()

    def access_token(self) -> str:
        """
        A bearer token for FCM, minted from the service account and cached.

        Refreshed a minute early. A token that expires between the check and the
        request produces a 401 that looks exactly like bad credentials, and
        chasing that is an afternoon nobody gets back.
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            if self._token and now < self._expires_at - timedelta(seconds=60):
                return self._token

            # Imported separately, because they fail for different reasons and
            # a single message covering both sent a real debugging session
            # after the wrong package for an hour. `google-auth` provides the
            # credentials; the transport it needs is a *separate* optional
            # dependency, and the one that is actually missing on a clean
            # deploy is `requests`.
            try:
                from google.oauth2 import service_account as google_sa
            except ImportError as exc:  # pragma: no cover
                raise PushNotConfigured(
                    "google-auth is not installed. Add google-auth to "
                    "requirements.txt and redeploy.") from exc

            try:
                from google.auth.transport.requests import Request as GoogleRequest
            except ImportError as exc:  # pragma: no cover
                raise PushNotConfigured(
                    "The 'requests' package is missing. google-auth needs it "
                    "for its HTTP transport and does not install it "
                    "automatically. Add requests to requirements.txt and "
                    "redeploy.") from exc

            try:
                creds = google_sa.Credentials.from_service_account_info(
                    self.service_account, scopes=[FCM_SCOPE])
                creds.refresh(GoogleRequest())
            except Exception as exc:
                raise PushSendFailed(
                    f"Firebase rejected the service account key: {exc}") from None

            self._token = creds.token
            self._expires_at = creds.expiry.replace(tzinfo=timezone.utc) if (
                creds.expiry and creds.expiry.tzinfo is None
            ) else (creds.expiry or now + timedelta(minutes=55))
            return self._token


#: Cached per project id. Rebuilt when the operator saves a different key, which
#: `reset_credentials_cache` does explicitly rather than leaving to a TTL - an
#: operator who has just pasted a corrected key should not wait an hour to find
#: out whether it works.
_cred_cache: dict[str, _Credentials] = {}
_cred_lock = threading.Lock()


def reset_credentials_cache() -> None:
    with _cred_lock:
        _cred_cache.clear()


def resolve_credentials(db: Session) -> _Credentials:
    """
    Where the Firebase key comes from, in priority order.

    Environment first, so a deployment already configured that way does not
    change behaviour and an operator cannot lock push out by saving a bad form.
    Platform settings second, which is what makes rotation possible without a
    redeploy.
    """
    raw = os.getenv("FIREBASE_CREDENTIALS_JSON")
    project = os.getenv("FIREBASE_PROJECT_ID")

    if not raw:
        row = db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
        if row is None or not row.fcm_credentials_encrypted:
            raise PushNotConfigured(
                "No Firebase credentials. A master admin can add the service "
                "account key under Platform settings, or it can be supplied as "
                "FIREBASE_CREDENTIALS_JSON in the environment.")
        raw = decrypt(row.fcm_credentials_encrypted)
        if raw is None:
            # SECRET_KEY was rotated after the key was stored, so the ciphertext
            # can no longer be read. Said plainly, because the fix is "paste the
            # key again" and no amount of retrying will do it.
            raise PushNotConfigured(
                "The stored Firebase key can no longer be decrypted - the "
                "application secret changed since it was saved. Paste the "
                "service account key again under Platform settings.")
        project = project or row.fcm_project_id

    try:
        service_account = json.loads(raw)
    except json.JSONDecodeError:
        raise PushNotConfigured(
            "The Firebase key is not valid JSON. Paste the whole downloaded "
            "file, from the opening brace to the closing one.") from None

    project = project or service_account.get("project_id")
    if not project:
        raise PushNotConfigured(
            "The Firebase key does not name a project. It should contain a "
            "\"project_id\" field - check you pasted the service account key "
            "and not google-services.json.")

    with _cred_lock:
        cached = _cred_cache.get(project)
        if cached is not None and cached.service_account == service_account:
            return cached
        creds = _Credentials(project, service_account)
        _cred_cache[project] = creds
        return creds


# --------------------------------------------------------------- the service
class PushService:
    def __init__(self, db: Session):
        self.db = db

    # ----------------------------------------------------------- device tokens
    def register(self, *, token: str, platform: str,
                 organization_id: uuid.UUID | None = None,
                 user_id: uuid.UUID | None = None,
                 resident_id: uuid.UUID | None = None) -> DeviceToken:
        """
        Record that this phone wants notifications for this person.

        Called on every app start, not only on first permission. Firebase
        rotates tokens on its own schedule - a reinstall, a restore from backup,
        a long gap between opens - so a token fetched once and stored for ever
        quietly stops working, and the only symptom is silence.

        An existing token is moved to the caller rather than duplicated. That is
        the case where a phone changes hands: without it, the previous
        occupant's rent reminders keep arriving on somebody else's screen.
        """
        if bool(user_id) == bool(resident_id):
            raise ValueError("exactly one of user_id / resident_id is required")

        now = datetime.now(timezone.utc)
        row = self.db.scalars(
            select(DeviceToken).where(DeviceToken.token == token)
            # Locked: two app starts a few milliseconds apart is the ordinary
            # case on a phone with a flaky connection, and both would otherwise
            # try to insert the same token.
            .with_for_update()).first()

        if row is None:
            row = DeviceToken(
                organization_id=organization_id, user_id=user_id,
                resident_id=resident_id, token=token, platform=platform,
                last_seen_at=now)
            self.db.add(row)
        else:
            row.organization_id = organization_id
            row.user_id = user_id
            row.resident_id = resident_id
            row.platform = platform
            row.last_seen_at = now
            row.revoked_at = None
            row.revoked_reason = None
        self.db.flush()
        return row

    def revoke(self, token: str, reason: str = "signed out") -> bool:
        """Stop sending to this phone. Used on sign-out."""
        row = self.db.scalars(
            select(DeviceToken).where(DeviceToken.token == token)).first()
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = datetime.now(timezone.utc)
        row.revoked_reason = reason[:60]
        self.db.flush()
        return True

    def recipient_wants_push(self, notification: Notification) -> bool:
        """
        Has this person switched notifications off in their own profile?

        Checked at send time rather than at write time. The in-app bell must
        still show everything - turning push off means "stop buzzing my phone",
        not "hide things from me", and a resident who silenced notifications
        still needs to find their invoice when they open the app.

        A recipient row that has since been deleted answers False rather than
        raising: the cascade will remove the notification too, and a sweep is
        the wrong place to discover a missing foreign key.
        """
        if notification.user_id:
            person = self.db.get(User, notification.user_id)
        else:
            person = self.db.get(Customer, notification.resident_id)
        return bool(person and person.notifications_enabled)

    def live_tokens_for(self, notification: Notification) -> list[DeviceToken]:
        stmt = select(DeviceToken).where(DeviceToken.revoked_at.is_(None))
        if notification.user_id:
            stmt = stmt.where(DeviceToken.user_id == notification.user_id)
        else:
            stmt = stmt.where(DeviceToken.resident_id == notification.resident_id)
        return list(self.db.scalars(stmt).all())

    # ------------------------------------------------------------- sending
    def _post(self, creds: _Credentials, message: dict) -> tuple[bool, str | None]:
        """
        One message to one token. Returns (delivered, error code).

        httpx rather than requests: it is already a dependency and the timeout
        is explicit. A hung Firebase call with no timeout would hold the sweep
        open indefinitely and the app would look frozen to nobody, because the
        sweep runs in the background - which is exactly the kind of failure that
        is never noticed until it has been happening for a month.
        """
        import httpx

        url = FCM_ENDPOINT.format(project=creds.project_id)
        try:
            response = httpx.post(
                url, json={"message": message}, timeout=20.0,
                headers={"Authorization": f"Bearer {creds.access_token()}",
                         "Content-Type": "application/json"})
        except httpx.HTTPError as exc:
            return False, f"network: {exc}"[:200]

        if response.status_code == 200:
            return True, None

        # Google's error body names the reason precisely. Kept, because
        # "UNREGISTERED" and "SENDER_ID_MISMATCH" call for opposite responses
        # and a generic failure would leave both looking identical.
        try:
            body = response.json()
            status = (body.get("error", {}).get("details", [{}])[0]
                      .get("errorCode")
                      or body.get("error", {}).get("status")
                      or str(response.status_code))
        except Exception:
            status = str(response.status_code)
        return False, str(status)[:200]

    def _build_message(self, notification: Notification, token: str) -> dict:
        """
        The FCM payload.

        `notification` (the visible part) and `data` (what the app reads on tap)
        are both sent. Notification-only would show a message that opens the
        home screen; data-only would deliver nothing while the app is closed,
        because Android needs the notification block to draw anything itself.

        Priority is high so the message is delivered during Doze rather than
        being batched until the phone is next unlocked - the difference between
        a rent reminder arriving now and arriving tomorrow morning.
        """
        return {
            "token": token,
            "notification": {
                "title": notification.title,
                "body": notification.message[:500],
            },
            "data": {
                "notification_id": str(notification.id),
                "kind": str(notification.kind),
                "link": notification.link or "/me/notifications",
                "entity_type": notification.entity_type or "",
                "entity_id": str(notification.entity_id or ""),
            },
            "android": {
                "priority": "high",
                "notification": {
                    # Must match the channel the app creates, or Android 8+
                    # drops the message without a word in any log.
                    "channel_id": "pgguru_default",
                    "icon": "ic_stat_notify",
                    "color": "#0F172A",
                    # Tapping opens the app rather than doing nothing. The app
                    # reads `link` out of `data` and routes from there.
                    "click_action": "FLUTTER_NOTIFICATION_CLICK",
                },
            },
        }

    def send_one(self, notification: Notification) -> tuple[int, str | None]:
        """
        Deliver one notification to every live phone of its recipient.

        Returns (phones delivered to, last error). Zero delivered with no error
        means the person simply has no device registered - not a failure, and
        the row is still marked sent so it is not swept for ever.
        """
        creds = resolve_credentials(self.db)
        tokens = self.live_tokens_for(notification)
        if not tokens:
            return 0, None

        delivered = 0
        last_error: str | None = None
        for device in tokens:
            ok_, error = self._post(creds, self._build_message(notification,
                                                               device.token))
            if ok_:
                delivered += 1
                device.last_seen_at = datetime.now(timezone.utc)
                continue
            last_error = error
            if error and any(dead in error for dead in DEAD_TOKEN_ERRORS):
                # The app was removed or the token replaced. Retire it rather
                # than retrying for ever against a phone that will never answer.
                device.revoked_at = datetime.now(timezone.utc)
                device.revoked_reason = f"firebase: {error}"[:60]
                log.info("Retired dead device token (%s)", error)
        self.db.flush()
        return delivered, last_error

    # ------------------------------------------------------------- the sweep
    def dispatch_pending(self, limit: int = BATCH_SIZE) -> dict:
        """
        Deliver every notification that has not been pushed yet.

        This is the one place push happens. It reads rows the other eight
        services wrote without knowing this existed.

        SKIP LOCKED is what makes it safe to run in more than one web worker:
        each sweep takes a different batch instead of two workers fighting over
        the same rows and delivering each of them twice.
        """
        row = self.db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
        if row is None or not row.notify_push_enabled:
            return {"sent": 0, "failed": 0, "skipped": 0, "reason": "push disabled"}

        stmt = (select(Notification)
                .where(Notification.pushed_at.is_(None),
                       Notification.push_attempts < MAX_PUSH_ATTEMPTS)
                .order_by(Notification.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True))
        pending = list(self.db.scalars(stmt).all())
        if not pending:
            return {"sent": 0, "failed": 0, "skipped": 0}

        now = datetime.now(timezone.utc)
        sent = failed = skipped = 0

        for notification in pending:
            # Audience toggles are applied here rather than at write time: the
            # in-app bell should still show everything even when an operator has
            # turned off push for that side.
            wanted = (row.push_to_staff if notification.user_id
                      else row.push_to_residents)
            if not wanted:
                notification.pushed_at = now
                notification.push_error = "audience disabled"
                skipped += 1
                continue

            if not self.recipient_wants_push(notification):
                notification.pushed_at = now
                notification.push_error = "recipient opted out"
                skipped += 1
                continue

            notification.push_attempts += 1
            try:
                delivered, error = self.send_one(notification)
            except PushNotConfigured as exc:
                # Nothing is wrong with the row, so do not burn its attempts.
                # Put the count back and stop the sweep - every other row in
                # this batch would fail identically.
                notification.push_attempts -= 1
                log.warning("Push not configured: %s", exc)
                break
            except PushSendFailed as exc:
                notification.push_error = str(exc)[:200]
                failed += 1
                continue

            if error and delivered == 0:
                notification.push_error = error
                failed += 1
                if notification.push_attempts >= MAX_PUSH_ATTEMPTS:
                    # Out of tries. Marked sent so it leaves the queue, with the
                    # reason kept on the row so it is still diagnosable.
                    notification.pushed_at = now
                continue

            notification.pushed_at = now
            notification.push_error = None
            sent += 1

        self.db.flush()
        return {"sent": sent, "failed": failed, "skipped": skipped}

    # ---------------------------------------------------------------- testing
    def send_test(self, *, user_id: uuid.UUID,
                  organization_id: uuid.UUID | None = None) -> int:
        """
        A message straight to the caller's own phones, bypassing the queue.

        For the "Send test notification" button. Proves delivery rather than
        configuration - a wrong project id or a revoked key both save perfectly
        and deliver nothing, and operators conflate the two constantly.
        """
        creds = resolve_credentials(self.db)
        tokens = list(self.db.scalars(
            select(DeviceToken).where(DeviceToken.user_id == user_id,
                                      DeviceToken.revoked_at.is_(None))).all())
        if not tokens:
            raise PushSendFailed(
                "No phone is registered for your account. Open the PGuru app "
                "on your phone, sign in, and allow notifications - then try "
                "again.")

        probe = Notification(
            id=uuid.uuid4(), organization_id=organization_id, user_id=user_id,
            kind="SYSTEM", title="PGuru test notification",
            message="Push notifications are working. This is a test.",
            link="/notifications")

        delivered = 0
        errors: list[str] = []
        for device in tokens:
            ok_, error = self._post(creds, self._build_message(probe, device.token))
            if ok_:
                delivered += 1
            elif error:
                errors.append(error)

        if delivered == 0:
            raise PushSendFailed(
                "Firebase accepted the request but delivered nothing: "
                + "; ".join(errors[:3]))
        return delivered