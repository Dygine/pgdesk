"""Request shapes for device registration and Firebase configuration."""
from typing import Literal

from pydantic import BaseModel, Field


class DeviceTokenRegister(BaseModel):
    """What the app posts on every start, not only on first permission."""

    token: str = Field(min_length=10, max_length=500)
    platform: Literal["android", "ios", "web"] = "android"


class DeviceTokenRevoke(BaseModel):
    token: str = Field(min_length=10, max_length=500)


class FcmCredentialsUpdate(BaseModel):
    """
    The service account JSON, whole, as downloaded from Firebase.

    Optional so that an empty body clears it - which is how an operator turns
    push off completely, distinct from omitting the field.
    """

    credentials: str | None = Field(default=None, max_length=8000)
    project_id: str | None = Field(default=None, max_length=120)


class NotificationPreferenceUpdate(BaseModel):
    """The one switch a person controls for themselves."""

    enabled: bool


class BroadcastRequest(BaseModel):
    """
    A platform-wide message from the operator to every app user.

    Separate from an Announcement, which belongs to one PG and is written by
    its owner. This one crosses tenants, so it is master-admin only and is
    never attributed to a PG.
    """

    title: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=3, max_length=2000)
    #: "all", "staff" (owners and their users) or "residents".
    audience: Literal["all", "staff", "residents"] = "all"
    #: Where tapping it goes. Defaults to the recipient's notification list.
    link: str | None = Field(default=None, max_length=200)
    #: Typed back by the sender to confirm. A message to every user of every PG
    #: cannot be recalled once the sweep has run, and "sent to 4,000 people by
    #: accident" is not a recoverable mistake.
    confirm: bool = False
