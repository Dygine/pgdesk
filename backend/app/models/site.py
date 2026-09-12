"""
The public website, stored as content rather than code.

Why this is a table and not an HTML file
----------------------------------------
The marketing site changes far more often than the product does - a price, a
phone number, a testimonial, a headline someone wants to try differently this
week. Every one of those was a code change, a build and a deploy, which meant
the person who wanted the change was never the person who could make it.

So the site is content in the database and the master admin edits it. Nobody
needs a developer to fix a typo on the homepage.

Shape: blocks, not columns
--------------------------
One row per *block* of the site - hero, features, pricing, testimonials,
contact, footer, seo - each holding a JSON body. Deliberately not a wide table
with a column per field: a marketing page grows a field every time someone has
an idea, and a schema migration per idea is exactly the friction this exists to
remove. The API validates shape on the way in, so the JSON is not a free-for-all.

`is_published` is per block. An owner can write the whole testimonials section,
leave it unpublished, and the site simply omits it until they are ready.

Images
------
Two routes, because they serve different people:

  url      - a link to an image hosted anywhere. This is how stock photography
             gets used, and it costs this database nothing.
  upload   - bytes stored here, capped at SITE_IMAGE_MAX_BYTES.

The cap is 120 KB, not the 5 KB that listing photos and ID scans get. Those are
thumbnails on a phone; this is a hero image on a laptop, and 5 KB of hero photo
looks like a mistake. Twelve images at 120 KB is 1.4 MB for the entire website,
which PostgreSQL does not notice and which no CDN bill is attached to.
"""
import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Integer, JSON, LargeBinary, String, Text, true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import Timestamps, UUIDPrimaryKey

#: Website images are not listing photos. See the module docstring.
SITE_IMAGE_MAX_BYTES = 120 * 1024
#: How many images the whole website may hold.
SITE_IMAGE_MAX_COUNT = 24

#: The blocks the website is built from, in the order they appear on the page.
#: A block the editor has never touched simply falls back to its preset.
SITE_BLOCKS = (
    "brand",        # name, tagline, logo, the "by <company>" line
    "hero",         # headline, sub-headline, the two buttons, hero image
    "trust",        # the strip of numbers under the hero
    "problem",      # what it replaces
    "features",     # the cards
    "screenshots",  # captioned images of the product
    "how",          # numbered steps
    "pricing",      # plans and what each includes
    "testimonials", # quotes, with attribution
    "faq",          # questions and answers
    "cta",          # the closing call to action
    "contact",      # phone, email, address, hours
    "footer",       # links, legal entity, copyright
    "seo",          # title, description, keywords, social image
)


class SiteBlock(Base, UUIDPrimaryKey, Timestamps):
    """One editable section of the public website."""

    __tablename__ = "site_blocks"

    #: One of SITE_BLOCKS. Unique: a block is a singleton.
    key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)

    #: Everything the block renders. Shape is validated per key by the schema,
    #: never trusted raw from the database into HTML.
    body: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    #: Unpublished blocks are omitted from the public payload entirely, so a
    #: half-written testimonials section is invisible rather than embarrassing.
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true())

    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Who last touched it. A marketing page with several editors needs this the
    #: first time two people disagree about a price.
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column()

    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_site_blocks_position"),
    )

    def __repr__(self) -> str:
        return f"<SiteBlock {self.key}>"


class SiteImage(Base, UUIDPrimaryKey, Timestamps):
    """
    A picture used somewhere on the website.

    Either `url` (hosted elsewhere - stock photography, a CDN) or `content`
    (bytes stored here). Exactly one, enforced by a CHECK, so nothing has to
    guess which one wins.

    `slot` is how a block finds its image: "hero", "screenshot-1", "feature-beds".
    The editor writes the slot name into the block body, and the site resolves it.
    Referring by slot rather than by id means an image can be swapped without the
    block that uses it being edited at all.
    """

    __tablename__ = "site_images"

    slot: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    #: Shown in the editor, and used as the alt text if the block gives none.
    #: Alt text is not optional decoration - it is what a screen reader reads out.
    alt_text: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    caption: Mapped[str | None] = mapped_column(String(200))

    url: Mapped[str | None] = mapped_column(Text)

    mime_type: Mapped[str | None] = mapped_column(String(20))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[bytes | None] = mapped_column(LargeBinary)

    __table_args__ = (
        CheckConstraint(
            "(url IS NOT NULL AND content IS NULL) "
            "OR (url IS NULL AND content IS NOT NULL)",
            name="ck_site_images_one_source"),
        CheckConstraint(
            f"content IS NULL OR octet_length(content) <= {SITE_IMAGE_MAX_BYTES}",
            name="ck_site_images_content_size"),
    )

    @property
    def is_hosted(self) -> bool:
        return self.url is not None

    def __repr__(self) -> str:
        return f"<SiteImage {self.slot}>"
