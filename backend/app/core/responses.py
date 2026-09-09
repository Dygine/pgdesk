"""Helpers so a router never hand-builds an envelope dict."""
from typing import Any

from app.schemas.common import PaginatedEnvelope, PaginationMeta


def ok(data: Any = None, message: str | None = None) -> dict:
    return {"success": True, "data": data, "message": message}


def paginated(items: list, page: int, page_size: int, total: int, message: str | None = None) -> dict:
    return {
        "success": True,
        "data": items,
        "pagination": PaginationMeta.build(page, page_size, total).model_dump(),
        "message": message,
    }
