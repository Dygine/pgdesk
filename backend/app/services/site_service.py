"""
Reading and writing the public website.

Two jobs: hand the site its content, and let the master admin change it.

The presets below are the site as it ships. They are real, usable copy rather
than lorem ipsum, because a site that reads like a placeholder is one nobody
trusts enough to edit - and because the first thing the master admin sees should
be something worth adjusting rather than something worth rewriting.

What the presets deliberately do NOT contain
--------------------------------------------
Invented proof. No "trusted by 2,000+ owners", no five-star testimonials from
people who do not exist, no revenue figure. Competitors lead with numbers like
those and some of them have earned them; claiming them before they are true is
false advertising, and the person who would answer for it is the account holder,
not the software.

So the trust strip ships with what is verifiable about the product itself
(bed-level tracking, a portal per resident, UPI and cash), the testimonials
block ships unpublished and empty, and the editor says plainly what each field
is for. Fill them in when they are true.
"""
from __future__ import annotations

import base64
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.site import (
    SITE_BLOCKS, SITE_IMAGE_MAX_BYTES, SITE_IMAGE_MAX_COUNT, SiteBlock, SiteImage,
)

# Placeholder photography.
#
# picsum.photos rather than a named stock library: it returns a real photograph
# for any seed, needs no key, and - the part that matters - is guaranteed to
# resolve. A hand-picked stock URL that 404s leaves a broken image on the
# homepage, which is worse than a generic one that loads.
#
# These are stand-ins. Every one is replaceable from Master -> Website in about
# a minute, and photographs of the actual property will always beat them.
def _photo(seed: str, w: int = 1200, h: int = 800) -> str:
    return f"https://picsum.photos/seed/{seed}/{w}/{h}"


#: The website as it ships. Every block the editor has not touched renders from
#: here, so the site is complete and coherent from the first page load.
PRESETS: dict[str, dict] = {
    "brand": {
        "name": "PGuru",
        "tagline": "PG and hostel operations, on one screen",
        "logo_slot": "logo",
        "company": "Dygine",
        "company_url": "https://dygine.com",
        "show_company": True,
    },
    "hero": {
        "headline": "Every bed, every rupee, every branch.",
        "subheadline": (
            "Rooms, residents, rent and complaints in one place - with a login for "
            "every tenant and a public listing that fills your empty beds."
        ),
        "primary_label": "Open the app",
        "primary_href": "/login",
        "secondary_label": "Find a PG",
        "secondary_href": "/find-pg",
        "image_slot": "hero",
    },
    "trust": {
        # Statements about what the product does, not claims about how many
        # people use it. Replace with real numbers once there are real numbers.
        "items": [
            {"value": "Bed-level", "label": "occupancy, not room-level guesswork"},
            {"value": "Every tenant", "label": "gets their own portal login"},
            {"value": "UPI · Cash · Bank", "label": "all recorded the same way"},
            {"value": "Multi-branch", "label": "one dashboard across properties"},
        ],
    },
    "problem": {
        "title": "What it replaces",
        "intro": (
            "Most PGs run on a register, a WhatsApp group and a month-end evening "
            "with a calculator. None of those tell you which bed is free tonight."
        ),
        "items": [
            {"before": "A register in the drawer",
             "after": "Every resident, room and bed, searchable from your phone"},
            {"before": "Chasing rent on WhatsApp",
             "after": "Dues, receipts and reminders that keep their own score"},
            {"before": "\u201cIs 204-B free?\u201d",
             "after": "Live bed status across every branch"},
            {"before": "Complaints lost in chat",
             "after": "A ticket per complaint, with who closed it and when"},
        ],
    },
    "features": {
        "title": "What's inside",
        "items": [
            {"icon": "bed", "image_slot": "feature-beds", "title": "Rooms and beds",
             "text": "Buildings, floors, rooms and individual beds. Vacant, occupied, "
                     "on notice or under maintenance - at a glance, per branch."},
            {"icon": "users", "title": "Residents and KYC",
             "text": "Full profiles, stay history and scanned ID documents held "
                     "against each resident, behind their own permission."},
            {"icon": "rupee", "image_slot": "feature-rent", "title": "Rent and payments",
             "text": "Invoices, part payments, dues and receipts. UPI, cash and bank "
                     "transfers all recorded the same way."},
            {"icon": "portal", "image_slot": "feature-portal", "title": "A portal for every tenant",
             "text": "Residents see their rent, raise complaints, book laundry and "
                     "give notice themselves - instead of messaging you."},
            {"icon": "search", "title": "Public listing",
             "text": "Show your free beds to people searching nearby. Enquiries land "
                     "in your inbox. No broker, no commission."},
            {"icon": "shield", "title": "Roles and permissions",
             "text": "A manager, a warden and an accountant should not see the same "
                     "screens. Build the roles you actually have."},
        ],
    },
    "screenshots": {
        "title": "The product, not a mockup",
        "items": [
            {"image_slot": "shot-dashboard", "caption": "Owner dashboard - occupancy and collections"},
            {"image_slot": "shot-beds", "caption": "Bed grid, live across every branch"},
            {"image_slot": "shot-findpg", "caption": "Find a PG - public search with a real map"},
            {"image_slot": "shot-portal", "caption": "The resident's own portal"},
        ],
    },
    "how": {
        "title": "How it works",
        "steps": [
            {"title": "Create your PG", "text": "Branches, buildings, floors, rooms and beds. Bulk-create rooms so this takes minutes, not an afternoon."},
            {"title": "Add your residents", "text": "Details, documents and bed assignment. Each one gets a portal login."},
            {"title": "Set rent once", "text": "Due dates and amounts. Invoices and reminders then run themselves."},
            {"title": "Fill empty beds", "text": "Publish your free beds to the public search and take enquiries directly."},
        ],
    },
    "pricing": {
        "title": "Pricing",
        "intro": "Monthly, per organisation. Every plan includes the resident portal "
                 "and the public listing.",
        "note": "Prices in Indian rupees. Taxes as applicable.",
        "cta_label": "Start free",
        "cta_href": "/signup",
        # Editable here rather than read from the code's plan table.
        #
        # It used to render straight from frontend/src/data/plans.js, which made
        # the one thing on a marketing page that changes most - the price - the
        # one thing that needed a developer. These are the published prices; the
        # plan table still governs what an account may actually do.
        "plans": [
            {"name": "Starter", "price": "1499", "period": "month",
             "summary": "1 branch · up to 60 beds", "popular": "",
             "features": "Rooms & beds, Residents, Rent & payments, Complaints, Basic reports"},
            {"name": "Professional", "price": "3999", "period": "month",
             "summary": "3 branches · up to 300 beds", "popular": "yes",
             "features": "Everything in Starter, Multi-branch, Custom roles, "
                         "Attendance & QR gate, Food & laundry, Visitors, Expenses"},
            {"name": "Business", "price": "8999", "period": "month",
             "summary": "10 branches · up to 1,200 beds", "popular": "",
             "features": "Everything in Professional, Assets & inventory, "
                         "Advanced reports, Audit log export, Announcement targeting"},
            {"name": "Enterprise", "price": "19999", "period": "month",
             "summary": "50 branches · up to 8,000 beds", "popular": "",
             "features": "Everything in Business, Franchise grouping, API access, "
                         "Custom SLA, Onboarding assistance"},
        ],
    },
    "testimonials": {
        # Ships empty and unpublished on purpose - see the module docstring.
        "title": "What owners say",
        "items": [],
    },
    "faq": {
        "title": "Questions",
        "items": [
            {"q": "Do my residents need to install anything?",
             "a": "No. The resident portal opens in any browser. There is an Android app "
                  "as well, for anyone who prefers one."},
            {"q": "Can I run more than one PG?",
             "a": "Yes. Branches are built in from the start, and the dashboard totals "
                  "across all of them or filters to one."},
            {"q": "What happens to my data if I stop?",
             "a": "It stays yours. Residents, payments and reports can be exported at "
                  "any time."},
            {"q": "Is my tenants' ID data safe?",
             "a": "Scanned documents sit behind a separate permission, so only staff you "
                  "explicitly allow can view them. Everything travels over HTTPS."},
        ],
    },
    "cta": {
        "headline": "Start with one branch.",
        "text": "Set up your rooms and beds, add a few residents, and see a month through. "
                "Nothing to install.",
        "primary_label": "Create your account",
        "primary_href": "/signup",
        "secondary_label": "Download for Android",
        "secondary_href": "/pgguru.apk",
        "image_slot": "cta",
    },
    "contact": {
        "title": "Talk to us",
        "phone": "",
        "whatsapp": "",
        "email": "hello@dygine.com",
        "address": "",
        "hours": "Monday to Saturday, 10am - 7pm IST",
        "map_url": "",
    },
    "footer": {
        "legal_name": "",
        "links": [
            {"label": "Find a PG", "href": "/find-pg"},
            {"label": "Sign in", "href": "/login"},
            {"label": "Privacy", "href": "/privacy"},
            {"label": "Terms", "href": "/terms"},
        ],
        "copyright": "",
    },
    "seo": {
        "title": "PGuru - PG and hostel management software for Indian owners",
        "description": (
            "Manage rooms, beds, residents, rent and complaints across every branch. "
            "A portal for each tenant and a public listing that fills empty beds. "
            "Web and Android."
        ),
        "keywords": "PG management software, hostel management software India, "
                    "paying guest software, PG software Bengaluru, bed management",
        "canonical": "https://pgguru.in/",
        "social_image_slot": "social",
        "locale": "en_IN",
    },
}

#: The images the site ships with, so nothing renders as a grey box on day one.
#:
#: `logo` points at the real logo file bundled with the front end rather than at
#: a remote URL - it is the one image that must never depend on a network it
#: does not control.
PRESET_IMAGES: dict[str, dict] = {
    "logo":            {"url": "/pgguru-logo.png",
                        "alt_text": "PGuru"},
    "hero":            {"url": _photo("pgguru-hero-room", 1400, 1000),
                        "alt_text": "A bright shared room in a well-run PG"},
    "shot-dashboard":  {"url": _photo("pgguru-dashboard", 1200, 780),
                        "alt_text": "The owner dashboard: occupancy and collections"},
    "shot-beds":       {"url": _photo("pgguru-beds", 1200, 780),
                        "alt_text": "The bed grid, live across every branch"},
    "shot-findpg":     {"url": _photo("pgguru-findpg", 1200, 780),
                        "alt_text": "Find a PG: public search on a real map"},
    "shot-portal":     {"url": _photo("pgguru-portal", 1200, 780),
                        "alt_text": "The resident's own portal"},
    "feature-beds":    {"url": _photo("pgguru-feature-beds", 900, 600),
                        "alt_text": "Rooms and beds"},
    "feature-rent":    {"url": _photo("pgguru-feature-rent", 900, 600),
                        "alt_text": "Rent and payments"},
    "feature-portal":  {"url": _photo("pgguru-feature-portal", 900, 600),
                        "alt_text": "A portal for every resident"},
    "cta":             {"url": _photo("pgguru-cta", 1600, 700),
                        "alt_text": "A PG common area"},
    "social":          {"url": _photo("pgguru-social", 1200, 630),
                        "alt_text": "PGuru - PG and hostel management"},
}


class SiteContentService:
    """
    The website's content.

    `public_payload()` is unauthenticated and must never leak anything the
    editor has not published. That is why it filters on `is_published` and
    never returns the editor's own metadata.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------- reading
    def _rows(self) -> dict[str, SiteBlock]:
        return {b.key: b for b in self.db.scalars(select(SiteBlock)).all()}

    def public_payload(self) -> dict:
        """
        The whole site, presets merged with whatever has been edited.

        Merged rather than replaced: a block saved with three of its five fields
        still renders the other two from the preset, so a partial edit can never
        blank out a section of the live website.
        """
        saved = self._rows()
        blocks: dict[str, dict] = {}
        for key in SITE_BLOCKS:
            row = saved.get(key)
            if row is not None and not row.is_published:
                continue
            preset = PRESETS.get(key, {})
            blocks[key] = {**preset, **(row.body if row else {})}
        return {"blocks": blocks, "images": self.images_payload()}

    def admin_payload(self) -> dict:
        """Everything, published or not, plus what the editor needs to know."""
        saved = self._rows()
        return {
            "blocks": [
                {
                    "key": key,
                    "body": {**PRESETS.get(key, {}), **(saved[key].body if key in saved else {})},
                    "is_published": saved[key].is_published if key in saved else True,
                    "customised": key in saved,
                    "preset": PRESETS.get(key, {}),
                    "updated_at": saved[key].updated_at.isoformat()
                    if key in saved and saved[key].updated_at else None,
                }
                for key in SITE_BLOCKS
            ],
            "images": self.images_payload(admin=True),
            "max_image_bytes": SITE_IMAGE_MAX_BYTES,
            "max_images": SITE_IMAGE_MAX_COUNT,
        }

    def images_payload(self, *, admin: bool = False) -> dict:
        out: dict[str, dict] = {}
        for slot, preset in PRESET_IMAGES.items():
            if preset.get("url"):
                out[slot] = {"slot": slot, "src": preset["url"],
                             "alt_text": preset.get("alt_text", ""), "preset": True}
        for row in self.db.scalars(select(SiteImage)).all():
            src = row.url if row.is_hosted else (
                f"data:{row.mime_type};base64,{base64.b64encode(row.content).decode()}")
            entry = {"slot": row.slot, "src": src, "alt_text": row.alt_text,
                     "caption": row.caption, "preset": False}
            if admin:
                entry["hosted"] = row.is_hosted
                entry["size_bytes"] = row.size_bytes
            out[row.slot] = entry
        return out

    # ------------------------------------------------------------- writing
    def save_block(self, key: str, *, body: dict, is_published: bool = True,
                   user_id: uuid.UUID | None = None) -> SiteBlock:
        if key not in SITE_BLOCKS:
            raise AppError(f"'{key}' is not a section of the website.", code="site_block_key")
        row = self.db.scalars(select(SiteBlock).where(SiteBlock.key == key)).first()
        if row is None:
            row = SiteBlock(key=key, body={}, position=SITE_BLOCKS.index(key))
            self.db.add(row)
        row.body = body
        row.is_published = is_published
        row.updated_by_id = user_id
        self.db.flush()
        return row

    def reset_block(self, key: str) -> None:
        """Back to the preset. Deleting the row is what 'reset' means here."""
        row = self.db.scalars(select(SiteBlock).where(SiteBlock.key == key)).first()
        if row is not None:
            self.db.delete(row)

    def save_image(self, slot: str, *, url: str | None = None, image: str | None = None,
                   alt_text: str = "", caption: str | None = None) -> SiteImage:
        from app.services.resident_service import decode_image, sniff_image

        slot = (slot or "").strip()[:60]
        if not slot:
            raise AppError("An image needs a slot name.", code="site_image_slot")
        if bool(url) == bool(image):
            raise AppError("Give either a link to an image or an uploaded file, not both.",
                           code="site_image_source")

        row = self.db.scalars(select(SiteImage).where(SiteImage.slot == slot)).first()
        if row is None:
            held = len(self.db.scalars(select(SiteImage)).all())
            if held >= SITE_IMAGE_MAX_COUNT:
                raise ConflictError(
                    f"The website can hold {SITE_IMAGE_MAX_COUNT} images. "
                    "Delete one to add another.", code="site_image_limit")
            row = SiteImage(slot=slot)
            self.db.add(row)

        row.alt_text = (alt_text or "").strip()[:160]
        row.caption = (caption or "").strip()[:200] or None

        if url:
            clean = url.strip()
            if not clean.startswith(("https://", "http://")):
                raise AppError("An image link must start with https://", code="site_image_url")
            row.url = clean
            row.content = None
            row.mime_type = row.size_bytes = row.width = row.height = None
        else:
            content = decode_image(image)
            if not content:
                raise AppError("That image is empty.", code="site_image_empty")
            if len(content) > SITE_IMAGE_MAX_BYTES:
                raise AppError(
                    f"Website images must be under {SITE_IMAGE_MAX_BYTES // 1024} KB. "
                    f"This one is {len(content) / 1024:.0f} KB.", code="site_image_too_large")
            mime = sniff_image(content)
            if mime is None:
                raise AppError("Only JPEG, PNG or WebP images are accepted.",
                               code="site_image_type")
            row.url = None
            row.content = content
            row.mime_type = mime
            row.size_bytes = len(content)
        self.db.flush()
        return row

    def delete_image(self, slot: str) -> None:
        row = self.db.scalars(select(SiteImage).where(SiteImage.slot == slot)).first()
        if row is None:
            raise NotFoundError("No image in that slot.")
        self.db.delete(row)
