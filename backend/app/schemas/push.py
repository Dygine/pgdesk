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
