"""
Authentication service.

All of the decision-making lives here rather than in the router, so the rules
can be unit tested without an HTTP client and reused by any future entry point
(a CLI, a background job, an admin impersonation flow).

Two policies worth stating explicitly because they look like bugs otherwise:

1. **A wrong email and a wrong password produce the identical response.** Anyone
   can hit /auth/login; telling them "no such account" turns the endpoint into a
   membership oracle for a PG's staff and residents.

2. **Account status is only revealed after the password checks out.** A
   suspended user gets a clear "your account is suspended" message - but only
   once they have proved they own the account. Before that they get the generic
   failure, so status cannot be probed either.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError, PermissionDeniedError
from app.core.security import (
    create_access_token, generate_opaque_token, hash_password, hash_token,
    needs_rehash, verify_password, waste_time_like_a_verify,
)
from app.models import PlatformSettings  # noqa: F401  (session length setting)
from app.models import (
    Branch, Customer, Organization, RefreshToken, Subscription, User,
)
from app.models.enums import (
    CustomerStatus, OrganizationStatus, PrincipalKind, UserStatus,
)
from app.permissions.catalog import MASTER_PERMISSIONS
from app.services.login_code_service import LoginCodeService
from app.schemas.auth import (
    AuthenticatedUser, BranchSummary, OrganizationSummary, RoleSummary, SubscriptionSummary,
)

GENERIC_FAILURE = "Email or password is incorrect."


@dataclass
class Principal:
    """A staff user or a resident, normalised so callers stop caring which."""

    kind: PrincipalKind
    id: uuid.UUID
    email: str
    name: str
    organization_id: uuid.UUID | None
    obj: User | Customer

    @property
    def is_user(self) -> bool:
        return self.kind == PrincipalKind.USER


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def _refresh_window(self, native: bool) -> timedelta:
        """
        How long a refresh token lives, by client.

        Browser: 24 hours, full stop. A laptop is shared, borrowed and left
        open in a way a phone is not, and the session lives in a cookie the
        person cannot see or manage. A day means an unattended machine is safe
        by tomorrow morning without anyone having to remember to sign out.

        Installed app: effectively forever, and renewed on every rotation, so
        the clock never runs down on someone who keeps using it. That is what
        every other app on the phone does, and the reasoning is that the device
        is personal, lock-screened, and the token sits in the app's private
        storage where no other app can read it. The number is a platform
        setting rather than a constant, so an operator who thinks ten years is
        too long for a manager's handset can shorten it without a code change.

        Signing out, changing a password and deactivating an account still
        revoke every session immediately, on both kinds of client. Permanent
        means "not expired by a timer", never "cannot be withdrawn".
        """
        if not native:
            return timedelta(hours=settings.browser_session_hours)
        try:
            from app.models.platform import SINGLETON_ID
            row = self.db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
            if row is not None and row.native_session_days:
                return timedelta(days=row.native_session_days)
        except Exception:
            # Settings unreadable during a migration window: fall back rather
            # than refusing a login over a preference.
            pass
        return timedelta(days=3650)

    # ------------------------------------------------------------ lookups --
    def _find_user(self, email: str) -> User | None:
        return self.db.scalars(select(User).where(User.email == email)).first()

    def _find_customer(self, email: str) -> Customer | None:
        """
        The resident row this email signs in to.

        An email is unique inside one PG, not across PGs, so someone who moved
        from one PG to another can still have a checked-out row at the first.
        The live row wins. A dead one is returned only when it is all there is,
        so that person hears "you have checked out" rather than a generic
        failure - and never, as before, whichever row the database found first.
        """
        rows = list(self.db.scalars(
            select(Customer).where(Customer.email == email)
            .order_by(Customer.created_at.desc())).all())
        for row in rows:
            if row.can_sign_in:
                return row
        return rows[0] if rows else None

    # ----------------------------------------------------- authentication --
    def authenticate(self, email: str, password: str) -> Principal:
        email = email.strip().lower()

        user = self._find_user(email)
        if user is not None:
            return self._authenticate_user(user, password)

        customer = self._find_customer(email)
        if customer is not None:
            return self._authenticate_customer(customer, password)

        # No such account. Burn the same time a real verify would, so the two
        # cases are not distinguishable by response latency.
        waste_time_like_a_verify()
        raise AuthenticationError(GENERIC_FAILURE)

    def _authenticate_user(self, user: User, password: str) -> Principal:
        if not verify_password(password, user.password_hash):
            raise AuthenticationError(GENERIC_FAILURE)

        # Password is correct from here on, so status may be described honestly.
        if user.status == UserStatus.SUSPENDED:
            raise PermissionDeniedError(
                "This account has been suspended. Contact your PG owner."
            )
        if user.status == UserStatus.DEACTIVATED or not user.is_active:
            raise PermissionDeniedError(
                "This account has been deactivated. Contact your PG owner to restore it."
            )
        if user.status == UserStatus.INVITED:
            raise PermissionDeniedError(
                "This invitation has not been accepted yet."
            )

        if not user.is_master_admin:
            org = self.db.get(Organization, user.organization_id)
            if org is None:
                raise AuthenticationError("This account is not attached to an organisation.")
            if org.status in (OrganizationStatus.SUSPENDED, OrganizationStatus.CANCELLED):
                raise PermissionDeniedError(
                    f"This organisation is {org.status.lower()}. "
                    "Contact the platform administrator."
                )

        # Opportunistic upgrade: if the stored hash uses outdated parameters we
        # have the plaintext right now and will not again until the next login.
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        user.last_login_at = datetime.now(timezone.utc)
        return Principal(
            kind=PrincipalKind.USER, id=user.id, email=user.email,
            name=user.name, organization_id=user.organization_id, obj=user,
        )

    def _authenticate_customer(self, customer: Customer, password: str) -> Principal:
        if not customer.password_hash:
            # Recorded as an enquiry, never given portal access. Indistinguishable
            # from a wrong password on purpose.
            waste_time_like_a_verify()
            raise AuthenticationError(GENERIC_FAILURE)

        if not verify_password(password, customer.password_hash):
            raise AuthenticationError(GENERIC_FAILURE)

        if not customer.is_active:
            raise PermissionDeniedError("This resident account has been deactivated.")
        if customer.status in (CustomerStatus.CHECKED_OUT, CustomerStatus.ARCHIVED):
            raise PermissionDeniedError(
                "This resident has checked out. The portal is no longer available."
            )

        org = self.db.get(Organization, customer.organization_id)
        if org and org.status in (OrganizationStatus.SUSPENDED, OrganizationStatus.CANCELLED):
            raise PermissionDeniedError(
                "This PG's account is not currently active. Please contact the front desk."
            )

        if needs_rehash(customer.password_hash):
            customer.password_hash = hash_password(password)

        customer.last_login_at = datetime.now(timezone.utc)
        return Principal(
            kind=PrincipalKind.CUSTOMER, id=customer.id, email=customer.email or "",
            name=customer.full_name, organization_id=customer.organization_id, obj=customer,
        )

    # ------------------------------------------------------------- tokens --
    def issue_tokens(
        self, principal: Principal, *, user_agent: str | None = None,
        ip: str | None = None, native: bool = False,
        family_id: uuid.UUID | None = None,
    ) -> tuple[str, str]:
        """
        A fresh access token and a fresh refresh token.

        `family_id` is supplied by a rotation, so the new token stays in the
        same device chain as the one it replaces. A login leaves it empty and a
        new family is minted - that is what makes the phone's chain and the
        laptop's chain separable later.
        """
        access = create_access_token(str(principal.id), principal=principal.kind.value)

        raw = generate_opaque_token()
        row = RefreshToken(
            token_hash=hash_token(raw),
            expires_at=datetime.now(timezone.utc) + self._refresh_window(native),
            user_agent=user_agent,
            ip_address=ip,
            family_id=family_id or uuid.uuid4(),
            is_native=bool(native),
        )
        if principal.is_user:
            row.user_id = principal.id
        else:
            row.customer_id = principal.id
        self.db.add(row)
        self.db.flush()
        return access, raw

    def rotate_refresh_token(
        self, raw_token: str, *, user_agent: str | None = None,
        ip: str | None = None, native: bool = False
    ) -> tuple[str, str, Principal]:
        """
        Single-use refresh with reuse detection, confined to one device.

        Presenting an already-rotated token is either a retry whose reply was
        lost, or a stolen token being replayed. `_is_lost_reply` separates the
        two where it can; where it cannot, the token chain is revoked.

        What changed, and why it matters
        --------------------------------
        Revocation used to take out every session for the account. So one
        unlucky refresh on a laptop signed out the owner's phone, the manager's
        phone and every resident app in the building - and the most common
        trigger was not theft at all but a deploy: the rotation commits, the
        instance is replaced mid-reply, the app retries with a token the server
        has already spent.

        Now only the presenting device's chain is revoked. A stolen token can
        still be used to mint tokens until the theft is noticed, exactly as
        before - but that was already true of the honest half of every ambiguous
        case, and the account-wide blast radius was buying nothing except
        spurious sign-outs. Real remedies stay account-wide: signing out, a
        password change, or deactivating the account still revoke everything.

        Session length is read from the stored row rather than from the caller's
        header. An app whose header is stripped by a proxy keeps its permanent
        session instead of being quietly downgraded to a browser one.
        """
        row = self.db.scalars(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
        ).first()

        if row is None:
            raise AuthenticationError("That refresh token is not valid.")

        # Once a chain is native it stays native, whatever this request claims.
        native = bool(native or row.is_native)
        family = row.family_id

        now = datetime.now(timezone.utc)
        if row.revoked_at is not None:
            successor = self.db.get(RefreshToken, row.replaced_by) if row.replaced_by else None
            if not self._is_lost_reply(row, successor, now):
                self._revoke_family(row)
                raise AuthenticationError(
                    "This session was already refreshed elsewhere. For safety this "
                    "device has been signed out - please sign in again."
                )
            # The replacement never reached the device, so nobody legitimate holds
            # it. Retire it: if it is ever presented, that IS theft and gets the
            # chain revoked. Then issue a fresh pair in the same family.
            successor.revoked_at = now
            principal = self._principal_from_token_row(row)
            access, raw = self.issue_tokens(principal, user_agent=user_agent, ip=ip,
                                            native=native, family_id=family)
            new_row = self.db.scalars(
                select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
            ).first()
            if new_row:
                row.replaced_by = new_row.id     # a second lost reply is covered too
            return access, raw, principal

        if row.expires_at <= now:
            raise AuthenticationError("Your session has expired. Sign in again.")

        principal = self._principal_from_token_row(row)
        row.revoked_at = now
        access, raw = self.issue_tokens(principal, user_agent=user_agent, ip=ip,
                                        native=native, family_id=family)
        new_row = self.db.scalars(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
        ).first()
        if new_row:
            row.replaced_by = new_row.id
        return access, raw, principal

    #: How long a rotated-out token may be presented again, if its replacement
    #: has never been used. See `_is_lost_reply`.
    ROTATION_GRACE = timedelta(minutes=10)

    def _is_lost_reply(self, row: RefreshToken, successor: RefreshToken | None,
                       now: datetime) -> bool:
        """
        Whether presenting an already-rotated token is a retry, not a theft.

        Strict single use signed people out for something that is not an attack:
        the app sends its token, the server rotates it, and the reply never
        arrives - the phone lost signal, a sleeping free-tier server answered
        after the app had given up waiting, or the app was closed mid-request.
        The app still holds the old token and asks again. Treating that as theft
        signed the user out of every device, typically right after a deploy,
        when the server is slowest to answer.

        It is a retry when all three hold: the token was rotated (not logged out
        or revoked by a password change), it happened within ROTATION_GRACE, and
        the replacement has never been used. That last condition is what keeps
        theft detection intact: once two parties are both using tokens from one
        chain, the replacement has been used and the old rule applies in full.
        The window a thief gains is narrow - a token stolen and used within ten
        minutes of the real device refreshing, before it refreshes again - and
        the moment the real device presents its own (now retired) token, every
        session is signed out.
        """
        return (
            successor is not None
            and successor.revoked_at is None
            and row.revoked_at is not None
            and now - row.revoked_at <= self.ROTATION_GRACE
            and row.expires_at > now
        )

    def _principal_from_token_row(self, row: RefreshToken) -> Principal:
        if row.user_id:
            user = self.db.get(User, row.user_id)
            if user is None or not user.is_active or user.status != UserStatus.ACTIVE:
                raise AuthenticationError("This account is no longer active.")
            return Principal(PrincipalKind.USER, user.id, user.email, user.name,
                             user.organization_id, user)

        customer = self.db.get(Customer, row.customer_id)
        if customer is None or not customer.can_sign_in:
            raise AuthenticationError("This account is no longer active.")
        return Principal(PrincipalKind.CUSTOMER, customer.id, customer.email or "",
                         customer.full_name, customer.organization_id, customer)

    def _revoke_family(self, row: RefreshToken) -> int:
        """
        Revoke one device's chain of tokens - not the whole account.

        A row written before families existed has no family id. Those are
        treated as a chain of one: the single row is revoked and nothing else,
        which is the conservative reading of "we cannot tell which device this
        was". They disappear within a day for browsers and on the next rotation
        for apps, so this is a migration-window path only.
        """
        now = datetime.now(timezone.utc)
        if row.family_id is None:
            row.revoked_at = now
            return 1
        rows = list(self.db.scalars(
            select(RefreshToken).where(
                RefreshToken.family_id == row.family_id,
                RefreshToken.revoked_at.is_(None),
            )
        ).all())
        for r in rows:
            r.revoked_at = now
        return len(rows)

    def revoke(self, raw_token: str) -> bool:
        row = self.db.scalars(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
        ).first()
        if row is None or row.revoked_at is not None:
            # Already gone. Logout is idempotent and never reports failure.
            return False
        row.revoked_at = datetime.now(timezone.utc)
        return True

    def revoke_all_sessions(self, principal: Principal) -> int:
        now = datetime.now(timezone.utc)
        column = RefreshToken.user_id if principal.is_user else RefreshToken.customer_id
        rows = list(self.db.scalars(
            select(RefreshToken).where(column == principal.id, RefreshToken.revoked_at.is_(None))
        ).all())
        for r in rows:
            r.revoked_at = now
        return len(rows)

    # ---------------------------------------------------------- passwords --
    def change_password(self, principal: Principal, current: str | None, new: str) -> None:
        """
        Change, or on first sign-in set, the caller's password.

        The current password may be left out only while the account is on an
        owner-issued temporary one (`must_change_password`). That is the state
        a resident is in after scanning a sign-in QR - they never saw the
        temporary password, and demanding it would strand them on this screen.
        Requiring it adds nothing there anyway: whoever holds this session got
        it with that temporary password or with the owner's QR, and both came
        from the PG. Once a password has been chosen the flag clears and the
        current password is required again, as it always was.
        """
        obj = principal.obj
        stored = obj.password_hash
        first_time = bool(obj.must_change_password)

        if current:
            if not stored or not verify_password(current, stored):
                raise AuthenticationError("Your current password is incorrect.")
        elif not first_time:
            # 409 rather than 401: a 401 makes the client try a token refresh
            # and resend, which is noise for a form that is simply incomplete.
            raise ConflictError("Enter your current password.",
                                code="current_password_required")
        if stored and verify_password(new, stored):
            raise ConflictError("The new password must be different from the current one.")

        obj.password_hash = hash_password(new)
        obj.must_change_password = False

        # Changing a password invalidates every session; that is the whole
        # point of changing it after a suspected compromise. The caller hands
        # the device that made this request a fresh pair afterwards.
        self.revoke_all_sessions(principal)
        if not principal.is_user:
            # A sign-in QR must not outlive the password it stood in for.
            LoginCodeService(self.db).revoke_all(obj.id)

    # ------------------------------------------------------ serialisation --
    def describe(self, principal: Principal) -> AuthenticatedUser:
        if principal.is_user:
            return self._describe_user(principal.obj)
        return self._describe_customer(principal.obj)

    def _subscription_summary(self, organization_id: uuid.UUID) -> SubscriptionSummary | None:
        sub = self.db.scalars(
            select(Subscription).where(
                Subscription.organization_id == organization_id,
                Subscription.is_current.is_(True),
            )
        ).first()
        if sub is None:
            return None
        return SubscriptionSummary(
            plan=sub.plan.name if sub.plan else None,
            status=sub.status,
            start_date=sub.start_date,
            end_date=sub.end_date,
            days_remaining=(sub.end_date - date.today()).days,
            limits=sub.effective_limits(),
        )

    def _organization_summary(self, organization_id: uuid.UUID | None) -> OrganizationSummary | None:
        if organization_id is None:
            return None
        org = self.db.get(Organization, organization_id)
        if org is None:
            return None
        return OrganizationSummary(
            id=org.id, name=org.name, slug=org.slug, status=org.status, city=org.city,
            subscription=self._subscription_summary(org.id),
        )

    def _describe_user(self, user: User) -> AuthenticatedUser:
        if user.is_master_admin:
            # Master admins hold no Role row - `roles` is tenant data. Their
            # authority is the fixed master namespace.
            permissions = sorted(MASTER_PERMISSIONS)
            roles: list[RoleSummary] = []
            branches: list[BranchSummary] = []
            all_branches = False
            portal = "master"
        else:
            permissions = sorted(user.permission_codes)
            roles = [RoleSummary.model_validate(r) for r in user.roles]
            all_branches = user.all_branches
            source = (
                self.db.scalars(
                    select(Branch).where(Branch.organization_id == user.organization_id)
                ).all()
                if all_branches else user.branches
            )
            branches = [BranchSummary.model_validate(b) for b in source]
            portal = "org"

        return AuthenticatedUser(
            id=user.id, name=user.name, email=user.email, phone=user.phone,
            employee_id=user.employee_id, principal="user", portal=portal,
            is_master_admin=user.is_master_admin, status=user.status,
            must_change_password=user.must_change_password, last_login_at=user.last_login_at,
            role=roles[0] if roles else None, roles=roles,
            organization=self._organization_summary(user.organization_id),
            branches=branches, all_branches=all_branches, permissions=permissions,
        )

    def _describe_customer(self, customer: Customer) -> AuthenticatedUser:
        branches = []
        if customer.branch_id:
            branch = self.db.get(Branch, customer.branch_id)
            if branch:
                branches = [BranchSummary.model_validate(branch)]

        return AuthenticatedUser(
            id=customer.id, name=customer.full_name, email=customer.email or "",
            phone=customer.phone, principal="customer", portal="customer",
            is_master_admin=False, status=customer.status,
            must_change_password=customer.must_change_password,
            last_login_at=customer.last_login_at,
            role=RoleSummary(id=uuid.UUID(int=0), name="Resident",
                             description="Sees only their own stay."),
            roles=[],
            organization=self._organization_summary(customer.organization_id),
            branches=branches, all_branches=False,
            # Residents hold no module permissions. Their portal is scoped by
            # identity, not by a permission list, so an empty list is correct
            # rather than an oversight.
            permissions=[],
        )
