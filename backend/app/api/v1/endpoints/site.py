"""
The public website's content.

One unauthenticated read and a set of master-admin writes.

`GET /site` is deliberately open. It is what the marketing page calls on load,
before anybody has signed in - so it must never return anything the editor has
not published, and it never returns editor metadata. That filtering happens in
SiteContentService.public_payload(), not here, so a second reader cannot forget
to apply it.

Everything that writes is gated by `require_master`. There is one public website
and it belongs to the platform; a PG owner reaching these gets 403 whatever they
send.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.core.dependencies import CurrentScope, DbSession, require_master
from app.core.responses import ok
from app.services.site_service import SiteContentService

router = APIRouter(tags=["site"])
Master = Annotated[CurrentScope, Depends(require_master)]


# ------------------------------------------------------------------ schemas
class BlockSave(BaseModel):
    """
    A whole block body, replacing what was there.

    `dict` rather than a model per block: the shapes differ per key and change
    as the page does, and the alternative is fourteen models that have to be
    edited in lockstep with the editor. The service validates the key; the
    editor owns the shape; nothing here is rendered as HTML, only as text.
    """

    body: dict = Field(default_factory=dict)
    is_published: bool = True


class ImageSave(BaseModel):
    slot: str = Field(min_length=1, max_length=60)
    #: A link to an image hosted elsewhere. Free, and costs the database nothing.
    url: str | None = Field(default=None, max_length=2000)
    #: Or the bytes, as a data URL or bare base64. Capped at 120 KB after decode.
    image: str | None = Field(default=None, max_length=200_000)
    alt_text: str = Field(default="", max_length=160)
    caption: str | None = Field(default=None, max_length=200)


# ------------------------------------------------------------------- public
@router.get("/site", summary="The public website's content")
def get_site(db: DbSession) -> dict:
    """Unauthenticated. Published blocks only."""
    return ok(SiteContentService(db).public_payload())


# ------------------------------------------------------------------- master
@router.get("/master/site", summary="Everything the website editor needs")
def admin_site(db: DbSession, _: Master) -> dict:
    return ok(SiteContentService(db).admin_payload())


@router.put("/master/site/blocks/{key}", summary="Save one section of the website")
def save_block(key: str, body: BlockSave, db: DbSession, scope: Master) -> dict:
    row = SiteContentService(db).save_block(
        key, body=body.body, is_published=body.is_published,
        user_id=scope.user.id if scope.user else None)
    db.commit()
    return ok({"key": row.key, "is_published": row.is_published},
              message="Saved. The website updates on its next load.")


@router.delete("/master/site/blocks/{key}", summary="Reset a section to its preset")
def reset_block(key: str, db: DbSession, _: Master) -> dict:
    SiteContentService(db).reset_block(key)
    db.commit()
    return ok(None, message="Reset to the original wording.")


@router.put("/master/site/images", status_code=status.HTTP_200_OK,
            summary="Set an image (a link, or an upload under 120 KB)")
def save_image(body: ImageSave, db: DbSession, _: Master) -> dict:
    row = SiteContentService(db).save_image(
        body.slot, url=body.url, image=body.image,
        alt_text=body.alt_text, caption=body.caption)
    db.commit()
    return ok({"slot": row.slot, "hosted": row.is_hosted, "size_bytes": row.size_bytes},
              message="Image saved.")


@router.delete("/master/site/images/{slot}", summary="Remove an image")
def delete_image(slot: str, db: DbSession, _: Master) -> dict:
    SiteContentService(db).delete_image(slot)
    db.commit()
    return ok(None, message="Image removed.")
