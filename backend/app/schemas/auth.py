"""
Authentication contracts.

Note what is absent: no schema here has a `password_hash` field, so there is no
code path that could serialise one by accident.
"""
import re
import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.schemas.common import ORMModel

# Deliberately not EmailStr.
#
# EmailStr enforces deliverability, which rejects the special-use TLDs (.local,
# .test, .invalid) that internal and demo accounts legitimately use - including
# the ones documented in this project's own README. At login the address is an
# identifier being looked up, not a mailbox being written to, so a shape check is
# the correct strictness. EmailStr is still used where an address must actually
# receive mail (invitations, password reset).
LoginEmail = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]
_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------ requests
class LoginRequest(BaseModel):
    email: LoginEmail
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _normalise(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_SHAPE.match(v):
            raise ValueError("Enter a valid email address.")
        return v

    # The example is deliberately not a real seeded account. /docs is served
    # wherever the API runs, and an example containing working credentials
    # publishes them to anyone who opens the schema.
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"email": "you@example.com", "password": "your-password"}
        }
    )


class RefreshRequest(BaseModel):
    """
    Optional in a browser: the refresh token arrives in an HttpOnly cookie and
    the body is empty. Non-browser clients, which have no cookie jar, send it
    here instead.
    """
    refresh_token: str | None = Field(default=None, min_length=10, max_length=500)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(
        default=None,
        description="Only for clients that hold the token themselves; browsers "
                    "send the session cookie instead.",
    )
    all_sessions: bool = Field(
        default=False,
        description="Revoke every session for this account, not just this one.",
    )


class ChangePasswordRequest(BaseModel):
    #: Optional only while the account is on an owner-issued temporary password
    #: (`must_change_password`). A resident who signed in by scanning a QR never
    #: saw that password, so asking for it would strand them - see
    #: AuthService.change_password.
    current_password: str | None = Field(default=None, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class QrLoginRequest(BaseModel):
    """The text inside a sign-in QR: `PGD1:L:<key>`."""
    code: str = Field(min_length=8, max_length=300)


# ----------------------------------------------------------------- responses
class BranchSummary(ORMModel):
    id: uuid.UUID
    name: str
    code: str
    city: str | None = None


class RoleSummary(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_system_role: bool = False
    all_branches: bool = False


class SubscriptionSummary(BaseModel):
    """Milestone 3 enforces plan limits; the context it needs is exposed here now."""
    plan: str | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    days_remaining: int | None = None
    limits: dict[str, int] = Field(default_factory=dict)


class OrganizationSummary(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    city: str | None = None
    subscription: SubscriptionSummary | None = None


class AuthenticatedUser(BaseModel):
    """
    What the client is told about itself.

    `portal` is what the React router keys off, and it is decided here rather
    than inferred in the browser from a role name.
    """
    id: uuid.UUID
    name: str
    email: str
    phone: str | None = None
    employee_id: str | None = None
    principal: str                      # "user" | "customer"
    portal: str                         # "master" | "org" | "customer"
    is_master_admin: bool = False
    status: str
    must_change_password: bool = False
    last_login_at: datetime | None = None

    role: RoleSummary | None = None
    roles: list[RoleSummary] = Field(default_factory=list)
    organization: OrganizationSummary | None = None
    branches: list[BranchSummary] = Field(default_factory=list)
    all_branches: bool = False
    permissions: list[str] = Field(default_factory=list)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds.")


class LoginResponse(TokenPair):
    user: AuthenticatedUser


# ------------------------------------------------------------ password reset
class ForgotPasswordRequest(BaseModel):
    """Step one. The only step that names an address."""

    email: LoginEmail


class VerifyOtpRequest(BaseModel):
    """
    Step two. Still carries the address, because the code alone is not unique -
    six digits collide across users constantly, and the pair is what identifies
    a pending reset.
    """

    email: LoginEmail
    code: str = Field(min_length=4, max_length=10)


class ResetPasswordRequest(BaseModel):
    """
    Step three. No email field, deliberately.

    The address is read back out of the verification token, so a caller who
    proved one address cannot reset a different one. Adding an email field here
    would reintroduce exactly that hole.
    """

    verification_token: str = Field(min_length=16, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)
