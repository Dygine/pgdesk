"""Aggregations for the master and owner dashboards. Read-only."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentScope
from app.models import (
    AuditLog, Bed, Branch, Building, Customer, Floor, Organization, Room,
    Subscription, SubscriptionPlan, User,
)
from app.models.enums import (
    BedStatus, CustomerStatus, OrganizationStatus, UserStatus,
)


class MasterDashboardService:
    def __init__(self, db: Session):
        self.db = db

    def overview(self) -> dict:
        counts = dict(self.db.execute(
            select(Organization.status, func.count(Organization.id))
            .group_by(Organization.status)
        ).all())

        total_orgs = sum(counts.values())
        beds = self.db.scalar(select(func.count(Bed.id))) or 0
        occupied = self.db.scalar(
            select(func.count(Bed.id)).where(Bed.status == BedStatus.OCCUPIED)) or 0

        today, soon = date.today(), date.today() + timedelta(days=30)
        expiring = list(self.db.execute(
            select(Organization, Subscription, SubscriptionPlan)
            .join(Subscription, Subscription.organization_id == Organization.id)
            .join(SubscriptionPlan, SubscriptionPlan.id == Subscription.plan_id)
            .where(Subscription.is_current.is_(True),
                   Subscription.end_date.between(today, soon))
            .order_by(Subscription.end_date)
        ).all())

        # MRR from list prices. Real billing lands with the payments phase; this
        # is labelled as an estimate everywhere it is shown.
        mrr = self.db.scalar(
            select(func.coalesce(func.sum(SubscriptionPlan.price), 0))
            .select_from(Subscription)
            .join(SubscriptionPlan, SubscriptionPlan.id == Subscription.plan_id)
            .join(Organization, Organization.id == Subscription.organization_id)
            .where(Subscription.is_current.is_(True),
                   Organization.status.in_([OrganizationStatus.ACTIVE,
                                            OrganizationStatus.EXPIRING]))
        ) or 0

        by_plan = [
            {"plan": name, "organizations": n, "price": price, "mrr": n * price}
            for name, price, n in self.db.execute(
                select(SubscriptionPlan.name, SubscriptionPlan.price,
                       func.count(Subscription.id))
                .join(Subscription, Subscription.plan_id == SubscriptionPlan.id)
                .where(Subscription.is_current.is_(True))
                .group_by(SubscriptionPlan.name, SubscriptionPlan.price,
                          SubscriptionPlan.sort_order)
                .order_by(SubscriptionPlan.sort_order)
            ).all()
        ]

        recent_orgs = list(self.db.scalars(
            select(Organization).order_by(Organization.created_at.desc()).limit(6)
        ).all())
        activity = list(self.db.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(12)
        ).all())

        return {
            "organizations": {
                "total": total_orgs,
                "active": counts.get(OrganizationStatus.ACTIVE, 0),
                "trial": counts.get(OrganizationStatus.TRIAL, 0),
                "expiring": counts.get(OrganizationStatus.EXPIRING, 0),
                "expired": counts.get(OrganizationStatus.EXPIRED, 0),
                "suspended": counts.get(OrganizationStatus.SUSPENDED, 0),
                "inactive": counts.get(OrganizationStatus.INACTIVE, 0),
                "cancelled": counts.get(OrganizationStatus.CANCELLED, 0),
                "by_status": {k: v for k, v in counts.items()},
            },
            "platform": {
                "branches": self.db.scalar(select(func.count(Branch.id))) or 0,
                "buildings": self.db.scalar(select(func.count(Building.id))) or 0,
                "rooms": self.db.scalar(select(func.count(Room.id))) or 0,
                "beds": beds,
                "occupied_beds": occupied,
                "occupancy_rate": round(occupied / beds * 100, 1) if beds else 0.0,
                "customers": self.db.scalar(
                    select(func.count(Customer.id)).where(
                        Customer.status.notin_([CustomerStatus.CHECKED_OUT,
                                                CustomerStatus.ARCHIVED]))) or 0,
                "users": self.db.scalar(select(func.count(User.id)).where(
                    User.is_master_admin.is_(False))) or 0,
            },
            "subscriptions": {
                "active": self.db.scalar(select(func.count(Subscription.id)).where(
                    Subscription.is_current.is_(True))) or 0,
                "expiring_soon": len(expiring),
                "estimated_mrr": int(mrr),
                "by_plan": by_plan,
            },
            "expiring": [
                {"id": str(o.id), "name": o.name, "status": o.status, "plan": p.name,
                 "end_date": s.end_date.isoformat(),
                 "days_remaining": (s.end_date - today).days}
                for o, s, p in expiring[:8]
            ],
            "recent_organizations": [
                {"id": str(o.id), "name": o.name, "city": o.city, "status": o.status,
                 "owner_name": o.owner_name, "created_at": o.created_at.isoformat()}
                for o in recent_orgs
            ],
            "recent_activity": [
                {"id": str(a.id), "module": a.module, "action": a.action,
                 "description": a.description, "user_name": a.user_name,
                 "created_at": a.created_at.isoformat()}
                for a in activity
            ],
        }


class OwnerDashboardService:
    def __init__(self, db: Session, scope: CurrentScope):
        self.db = db
        self.scope = scope

    def overview(self, branch_id: uuid.UUID | None = None) -> dict:
        org_id = self.scope.organization_id
        branch_ids = [branch_id] if branch_id else list(self.scope.branch_ids)
        if branch_id and not self.scope.owns_branch(branch_id):
            branch_ids = []

        def count(model, *extra):
            if not branch_ids:
                return 0
            stmt = select(func.count(model.id)).where(model.organization_id == org_id)
            if hasattr(model, "branch_id"):
                stmt = stmt.where(model.branch_id.in_(branch_ids))
            for clause in extra:
                stmt = stmt.where(clause)
            return self.db.scalar(stmt) or 0

        beds = count(Bed)
        occupied = count(Bed, Bed.status == BedStatus.OCCUPIED)
        available = count(Bed, Bed.status == BedStatus.AVAILABLE)

        by_branch = []
        for branch in self.db.scalars(
            select(Branch).where(Branch.organization_id == org_id,
                                 Branch.id.in_(branch_ids or [uuid.UUID(int=0)]))
            .order_by(Branch.name)
        ).all():
            b_total = self.db.scalar(select(func.count(Bed.id)).where(
                Bed.branch_id == branch.id)) or 0
            b_occ = self.db.scalar(select(func.count(Bed.id)).where(
                Bed.branch_id == branch.id, Bed.status == BedStatus.OCCUPIED)) or 0
            by_branch.append({
                "id": str(branch.id), "name": branch.name, "code": branch.code,
                "status": branch.status, "beds": b_total, "occupied": b_occ,
                "available": self.db.scalar(select(func.count(Bed.id)).where(
                    Bed.branch_id == branch.id, Bed.status == BedStatus.AVAILABLE)) or 0,
                "rooms": self.db.scalar(select(func.count(Room.id)).where(
                    Room.branch_id == branch.id)) or 0,
                "occupancy_rate": round(b_occ / b_total * 100, 1) if b_total else 0.0,
            })

        bed_status = {
            s.value.lower(): count(Bed, Bed.status == s.value) for s in BedStatus
        }

        activity = list(self.db.scalars(
            select(AuditLog).where(AuditLog.organization_id == org_id)
            .order_by(AuditLog.created_at.desc()).limit(10)
        ).all())

        return {
            "property": {
                "branches": len(branch_ids),
                "buildings": count(Building),
                "floors": count(Floor),
                "rooms": count(Room),
                "beds": beds,
                "occupied_beds": occupied,
                "available_beds": available,
                "occupancy_rate": round(occupied / beds * 100, 1) if beds else 0.0,
                "bed_status": bed_status,
            },
            "people": {
                "customers": count(
                    Customer,
                    Customer.status.notin_([CustomerStatus.CHECKED_OUT,
                                            CustomerStatus.ARCHIVED])),
                "active_staff": self.db.scalar(
                    select(func.count(User.id)).where(
                        User.organization_id == org_id,
                        User.status == UserStatus.ACTIVE)) or 0,
            },
            "by_branch": by_branch,
            # Rent, complaints and payments arrive with their own phases; the
            # keys are present so the dashboard does not need reshaping later.
            "pending": {"complaints": 0, "payments": 0, "upcoming_rent": 0},
            "recent_activity": [
                {"id": str(a.id), "module": a.module, "action": a.action,
                 "description": a.description, "user_name": a.user_name,
                 "created_at": a.created_at.isoformat()}
                for a in activity
            ],
        }
