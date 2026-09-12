"""
The v1 router tree.

Milestone 1 mounts meta only. The remaining routers are listed here as comments
in the order they will be built, so the shape of the finished API is visible
from one file rather than discovered by grepping.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    public, seeker,
    accounts, auth, billing, dashboard, master, me, meta, operations, property, rbac,
    residents, site, staff, support,
)

api_router = APIRouter()

api_router.include_router(public.router)
api_router.include_router(site.router)          # /site (public), /master/site/* (editor)
api_router.include_router(seeker.router)        # /public/seeker/*  PG-seeker accounts
api_router.include_router(auth.router)          # /auth
api_router.include_router(meta.router)          # /meta
api_router.include_router(master.router)        # /master/*   (platform operator)
api_router.include_router(dashboard.router)     # /dashboard, /subscription
api_router.include_router(property.router)      # /branches, /buildings, /floors, /rooms, /beds
api_router.include_router(rbac.router)          # /roles, /permissions, /users, /user-branches
api_router.include_router(residents.router)     # /residents/*                       Phase 5
api_router.include_router(billing.router)       # /invoices, /payments, /rent        Phase 6
api_router.include_router(operations.router)    # attendance, scan, visitors,
                                                # gate passes, food, laundry   Phases 7-10
api_router.include_router(support.router)       # complaints, queries, expenses,
                                                # inventory, assets, announcements,
                                                # settings, notifications,
                                                # reports                     Phases 11-16
api_router.include_router(staff.router)        # /staff  the workforce list, salaries
api_router.include_router(accounts.router)     # /accounts/pnl
api_router.include_router(me.router)            # /me/*  the resident portal
