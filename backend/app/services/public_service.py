"""
The public side: finding a PG, and asking about one.

Everything here is reachable without a login, which makes it the only part of
the system where the caller is nobody. Three rules follow from that and they
are the reason this lives in its own module rather than being a flag on the
existing services:

  1. Only branches that opted in are visible. `listed_publicly` is false by
     default and nothing here ever ignores it.
  2. Only fields chosen for publication are returned. Not the address column
     wholesale, not resident counts, not the gate token, not the geofence.
  3. Vacancy is published as a band, never a number.

The third one deserves its reasoning. "4 beds free" is what a seeker wants and
also exactly what a competitor wants: sample it weekly across a city and you
have every rival's occupancy curve, which is commercially sensitive in a way an
owner ticking "list my PG" is not agreeing to. A band answers the seeker's real
question - can I get in - while being far less useful to scrape.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Numeric, and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Bed, Branch, Organization, PgEnquiry, Room
from app.models.enums import (
    BedStatus, BranchStatus, NotificationType, OrganizationStatus,
)
from app.services.notification_service import NotificationService
from app.utils.geo import haversine_metres, is_valid_coordinate

#: How far a "near me" search reaches by default, and the most it will reach.
DEFAULT_RADIUS_KM = 5.0
MAX_RADIUS_KM = 50.0

MAX_RESULTS = 60


def _vacancy_band(free: int) -> str:
    """
    A description rather than a count. See the module docstring.

    The bands are shaped around the decision a seeker is making: none at all,
    hurry, or take your time.
    """
    if free <= 0:
        return "full"
    if free <= 3:
        return "a few beds"
    if free <= 10:
        return "several beds"
    return "plenty of beds"


class PublicService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------- search
    def search(self, *, latitude: float | None = None, longitude: float | None = None,
               radius_km: float | None = None, city: str | None = None,
               query: str | None = None, max_rent: float | None = None,
               gender: str | None = None, only_vacant: bool = False,
               limit: int = 20) -> list[dict]:
        """
        Listed PGs, nearest first when a position is given.

        Distance is computed in Python rather than SQL. PostGIS is not a
        dependency here and writing the haversine into raw SQL to sort on it
        would tie the query to one database for a result set that is capped at
        sixty rows anyway. If listings ever run to thousands per city this
        becomes a bounding-box query first; it is not that today, and pretending
        otherwise would be the more expensive mistake.
        """
        limit = max(1, min(limit, MAX_RESULTS))

        stmt = (
            select(Branch)
            .join(Organization, Organization.id == Branch.organization_id)
            .where(
                Branch.listed_publicly.is_(True),
                Branch.status == BranchStatus.ACTIVE,
                # A suspended or cancelled tenant disappears from search. Their
                # data is untouched - suspension freezes, it does not delete -
                # but sending a seeker to a PG whose owner cannot log in to
                # answer them helps nobody.
                Organization.status.in_(
                    [OrganizationStatus.ACTIVE, OrganizationStatus.TRIAL]),
            )
        )

        if city:
            stmt = stmt.where(func.lower(Branch.city) == city.strip().lower())
        if gender and gender.upper() in ("MALE", "FEMALE"):
            # "ANY" and unset both match a gendered search: a co-ed PG is a
            # valid answer for someone filtering on male or female.
            stmt = stmt.where(or_(Branch.gender_preference.is_(None),
                                  Branch.gender_preference == "ANY",
                                  Branch.gender_preference == gender.upper()))
        if max_rent is not None:
            # A listing with no price is kept rather than filtered out. Plenty
            # of PGs quote on enquiry, and dropping them would make the filter
            # quietly narrower than the seeker asked for.
            stmt = stmt.where(or_(Branch.starting_rent.is_(None),
                                  Branch.starting_rent <= max_rent))
        if query:
            like = f"%{query.strip()}%"
            stmt = stmt.where(or_(Branch.name.ilike(like),
                                  Organization.name.ilike(like),
                                  Branch.listing_headline.ilike(like),
                                  Branch.listing_description.ilike(like),
                                  Branch.city.ilike(like),
                                  Branch.address.ilike(like)))

        rows = list(self.db.scalars(stmt.limit(MAX_RESULTS * 2)).all())

        near = is_valid_coordinate(latitude, longitude)
        reach_m = min(radius_km or DEFAULT_RADIUS_KM, MAX_RADIUS_KM) * 1000

        out = []
        for branch in rows:
            distance = None
            if near:
                if branch.latitude is None or branch.longitude is None:
                    # Cannot be placed on a map, so it cannot answer "near me".
                    # Included in a text search, excluded from a location one.
                    continue
                distance = haversine_metres(
                    latitude, longitude, branch.latitude, branch.longitude)
                if distance > reach_m:
                    continue

            options, free = self._room_options(branch.id)
            if only_vacant and free <= 0:
                continue

            out.append(self._listing(branch, free, distance, options=options))

        if near:
            out.sort(key=lambda r: r["distance_m"])
        else:
            # Without a position, cheapest first, and unpriced listings last so
            # they do not crowd out the ones that answered the question.
            out.sort(key=lambda r: (r["starting_rent"] is None,
                                    r["starting_rent"] or 0))
        return out[:limit]

    def _room_options(self, branch_id: uuid.UUID) -> tuple[list[dict], int]:
        """
        Which kinds of room have a free bed, and what they start at.

        "Double sharing from 7,500 - a few beds" answers the question a seeker
        actually has far better than one band for the whole building. Each room
        type still gets a band, never a count, for the reason in the module
        docstring; the total is returned separately for the building-level band
        and is never published as a number.

        The rent is the bed's own price where one is set and the room's
        otherwise, the same precedence check-in uses.
        """
        rows = self.db.execute(
            select(Room.room_type, Room.capacity, Bed.rent_amount, Room.rent_amount)
            .join(Room, Room.id == Bed.room_id)
            .where(Bed.branch_id == branch_id, Bed.status == BedStatus.AVAILABLE)
        ).all()

        groups: dict[str, dict] = {}
        for room_type, capacity, bed_rent, room_rent in rows:
            label = (room_type or "Room").strip() or "Room"
            rent = float(bed_rent or 0) or float(room_rent or 0) or None
            g = groups.setdefault(label, {"free": 0, "rent": None, "sharing": capacity})
            g["free"] += 1
            if rent is not None and (g["rent"] is None or rent < g["rent"]):
                g["rent"] = rent
            if capacity and (not g["sharing"] or capacity < g["sharing"]):
                g["sharing"] = capacity

        options = [
            {"room_type": label, "sharing": g["sharing"] or None,
             "from_rent": g["rent"], "vacancy": _vacancy_band(g["free"])}
            for label, g in groups.items()
        ]
        options.sort(key=lambda o: (o["sharing"] or 99, o["from_rent"] or 0))
        return options, len(rows)

    def _listing(self, branch: Branch, free: int, distance: float | None, *,
                 options: list[dict] | None = None) -> dict:
        """
        Exactly the fields chosen for publication, listed one by one.

        Written out rather than serialised from the model on purpose: a column
        added to `branches` next year must not appear on a public page because
        a loop copied everything it found.
        """
        org = self.db.get(Organization, branch.organization_id)
        return {
            "id": str(branch.id),
            "pg_name": org.name if org else None,
            "name": branch.name,
            "headline": branch.listing_headline,
            "description": branch.listing_description,
            "city": branch.city,
            "address": branch.address,
            "latitude": branch.latitude,
            "longitude": branch.longitude,
            "starting_rent": float(branch.starting_rent) if branch.starting_rent else None,
            "gender_preference": branch.gender_preference or "ANY",
            "amenities": branch.amenities or [],
            "contact_phone": branch.contact_phone_public,
            "vacancy": _vacancy_band(free),
            "has_vacancy": free > 0,
            "room_options": options or [],
            "distance_m": round(distance, 1) if distance is not None else None,
        }

    def areas_matching(self, query: str, *, limit: int = 6) -> list[dict]:
        """
        Listed, positioned PGs whose city or address matches - the fallback
        "place" list when the geocoder is down or knows nothing.
        """
        like = f"%{(query or '').strip()}%"
        rows = self.db.scalars(
            select(Branch).join(Organization, Organization.id == Branch.organization_id)
            .where(Branch.listed_publicly.is_(True),
                   Branch.status == BranchStatus.ACTIVE,
                   Organization.status.in_(
                       [OrganizationStatus.ACTIVE, OrganizationStatus.TRIAL]),
                   Branch.latitude.is_not(None), Branch.longitude.is_not(None),
                   or_(Branch.city.ilike(like), Branch.address.ilike(like),
                       Branch.name.ilike(like)))
            .limit(limit)).all()
        return [
            {"label": ", ".join(p for p in (b.name, b.city) if p),
             "detail": b.address or b.city or b.name,
             "latitude": b.latitude, "longitude": b.longitude}
            for b in rows
        ]

    def get_listing(self, branch_id: uuid.UUID) -> dict:
        branch = self.db.scalars(select(Branch).where(
            Branch.id == branch_id, Branch.listed_publicly.is_(True),
            Branch.status == BranchStatus.ACTIVE)).first()
        if branch is None:
            # 404 for both "no such branch" and "not listed", so this endpoint
            # cannot be used to discover which PGs exist but chose privacy.
            raise NotFoundError("That PG listing is not available.")
        options, free = self._room_options(branch.id)
        return self._listing(branch, free, None, options=options)

    # ----------------------------------------------------------- enquiries
    def create_enquiry(self, *, branch_id: uuid.UUID, full_name: str, email: str,
                       phone: str | None, message: str | None,
                       move_in_date=None, ip: str | None = None) -> PgEnquiry:
        """
        Record an enquiry against a listed branch.

        The organisation is read from the branch, never from the request. That
        is the same rule every authenticated write in this codebase follows, and
        it matters more here, not less: the caller is anonymous, so there is no
        session to fall back on if the body were trusted.
        """
        branch = self.db.scalars(select(Branch).where(
            Branch.id == branch_id, Branch.listed_publicly.is_(True),
            Branch.status == BranchStatus.ACTIVE)).first()
        if branch is None:
            raise NotFoundError("That PG listing is not available.")

        address = (email or "").strip().lower()

        # Same person, same PG, still unanswered: update rather than pile up a
        # second row. An owner's inbox filling with duplicates from one anxious
        # seeker is how an inbox stops being read.
        existing = self.db.scalars(select(PgEnquiry).where(
            PgEnquiry.email == address, PgEnquiry.branch_id == branch_id,
            PgEnquiry.status == "NEW")).first()
        if existing is not None:
            existing.full_name = full_name.strip()
            existing.phone = phone or existing.phone
            existing.message = message or existing.message
            existing.move_in_date = move_in_date or existing.move_in_date
            self.db.flush()
            return existing

        row = PgEnquiry(
            organization_id=branch.organization_id, branch_id=branch.id,
            full_name=full_name.strip(), email=address, phone=phone,
            message=message, move_in_date=move_in_date,
            email_verified=True, requested_ip=ip)
        self.db.add(row)
        self.db.flush()

        # A lead nobody sees is not a lead. The bell is where staff already
        # look; the Enquiries inbox is where they act on it.
        NotificationService(self.db).to_permission_holders(
            branch.organization_id, "customers.view", NotificationType.SYSTEM,
            "New enquiry",
            f"{row.full_name} is asking about a bed at {branch.name}.",
            branch_id=branch.id, entity_type="enquiry", entity_id=row.id)
        return row
