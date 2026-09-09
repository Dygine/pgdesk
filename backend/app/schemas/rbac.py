"""Role, permission and user contracts."""
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class PermissionOut(ORMModel):
    id: uuid.UUID
    code: str
    module: str
    action: str
    label: str


class RoleOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_system_role: bool
    all_branches: bool
    permissions: list[str] = Field(default_factory=list)
    user_count: int = 0


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = None
    all_branches: bool = False
    permissions: list[str] = Field(
        default_factory=list,
        description="module.action codes. '*' and 'module.*' are expanded server-side.",
    )


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    all_branches: bool | None = None
    permissions: list[str] | None = None


class UserBranchSummary(ORMModel):
    id: uuid.UUID
    name: str
    code: str


class UserOut(ORMModel):
    id: uuid.UUID
    name: str
    email: str
    phone: str | None = None
    employee_id: str | None = None
    status: str
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None = None
    created_at: datetime
    roles: list[RoleOut] = Field(default_factory=list)
    branches: list[UserBranchSummary] = Field(default_factory=list)
    all_branches: bool = False
    permissions: list[str] = Field(default_factory=list)


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: str | None = None
    employee_id: str | None = None
    role_id: uuid.UUID
    branch_ids: list[uuid.UUID] = Field(default_factory=list)
    status: str | None = None
    password: str | None = Field(
        default=None, min_length=8,
        description="Omit to have a temporary password generated.",
    )


class UserUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    employee_id: str | None = None
    role_id: uuid.UUID | None = None
    branch_ids: list[uuid.UUID] | None = None
    status: str | None = None


class BranchAssignment(BaseModel):
    branch_ids: list[uuid.UUID]


class TemporaryCredentials(BaseModel):
    name: str
    email: str
    temporary_password: str
    must_change_password: bool = True
