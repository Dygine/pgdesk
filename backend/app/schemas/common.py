"""
The response envelope every endpoint returns, and the pagination contract every
list endpoint accepts. Defined once so no router invents its own shape.
"""
from math import ceil
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Envelope(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str | None = None


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int

    @classmethod
    def build(cls, page: int, page_size: int, total: int) -> "PaginationMeta":
        return cls(
            page=page, page_size=page_size, total=total,
            total_pages=max(1, ceil(total / page_size)) if page_size else 1,
        )


class PaginatedEnvelope(BaseModel, Generic[T]):
    success: bool = True
    data: list[T] = Field(default_factory=list)
    pagination: PaginationMeta
    message: str | None = None


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorEnvelope(BaseModel):
    success: bool = False
    message: str
    errors: list[ErrorDetail] = Field(default_factory=list)
    code: str | None = None


class PageParams(BaseModel):
    """Shared query parameters for list endpoints (item 42)."""
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=200)] = 20
    search: str | None = None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class HealthStatus(BaseModel):
    status: str
    environment: str
    version: str


class DatabaseHealth(BaseModel):
    status: str
    database: str
    server_version: str | None = None
    detail: str | None = None
