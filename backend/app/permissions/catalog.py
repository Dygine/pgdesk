"""
The permission catalogue.

This is a line-for-line mirror of the React app's `src/data/permissions.js`.
Both sides speak "<module>.<action>". If they ever drift, the UI shows a button
the API refuses - the worst possible failure mode - so `tests/test_permission_
catalog.py` parses the JavaScript file and asserts the two lists are identical.

Change one, change both.
"""

PERMISSION_MODULES: list[dict] = [
    {"key": "dashboard",     "label": "Dashboard",           "actions": ["view"]},
    {"key": "branches",      "label": "Branches",            "actions": ["view", "create", "edit", "delete"]},
    {"key": "property",      "label": "Buildings & floors",  "actions": ["view", "create", "edit", "delete"]},
    {"key": "buildings",     "label": "Buildings",           "actions": ["view", "create", "edit", "delete"]},
    {"key": "floors",        "label": "Floors",              "actions": ["view", "create", "edit", "delete"]},
    {"key": "rooms",         "label": "Rooms",               "actions": ["view", "create", "edit", "delete"]},
    {"key": "beds",          "label": "Beds",                "actions": ["view", "create", "edit", "delete", "assign", "transfer", "block"]},
    {"key": "customers",     "label": "Residents",           "actions": ["view", "create", "edit", "delete", "checkin", "checkout", "transfer", "assign_bed", "kyc_view", "kyc_verify"]},
    {"key": "rent",          "label": "Rent",                "actions": ["view", "manage", "generate"]},
    {"key": "invoices",      "label": "Rent & invoices",     "actions": ["view", "create", "edit", "delete", "cancel"]},
    {"key": "payments",      "label": "Payments",            "actions": ["view", "create", "edit", "delete", "verify", "refund"]},
    {"key": "expenses",      "label": "Expenses",            "actions": ["view", "create", "edit", "delete"]},
    {"key": "complaints",    "label": "Complaints",          "actions": ["view", "create", "assign", "update", "close", "manage"]},
    {"key": "food",          "label": "Food & mess",         "actions": ["view", "manage", "mark"]},
    {"key": "laundry",       "label": "Laundry",             "actions": ["view", "manage", "book"]},
    {"key": "scan",          "label": "QR gate scan",        "actions": ["view", "manage"]},
    {"key": "attendance",    "label": "Attendance",          "actions": ["view", "manage", "mark"]},
    {"key": "visitors",      "label": "Visitors",            "actions": ["view", "create", "approve", "manage"]},
    {"key": "gatepass",      "label": "Gate passes",         "actions": ["view", "create", "approve", "manage"]},
    {"key": "notifications", "label": "Notifications",       "actions": ["view", "manage"]},
    {"key": "announcements", "label": "Announcements",       "actions": ["view", "create", "edit", "delete"]},
    {"key": "queries",       "label": "Query centre",        "actions": ["view", "create", "respond", "manage"]},
    {"key": "staff",         "label": "Staff",               "actions": ["view", "create", "edit", "deactivate"]},
    {"key": "inventory",     "label": "Inventory",           "actions": ["view", "create", "manage", "adjust"]},
    {"key": "assets",        "label": "Assets",              "actions": ["view", "create", "manage"]},
    {"key": "reports",       "label": "Reports",             "actions": ["view", "export"]},
    {"key": "audit",         "label": "Audit log",           "actions": ["view", "export"]},
    {"key": "users",         "label": "Users",               "actions": ["view", "create", "edit", "deactivate"]},
    {"key": "roles",         "label": "Roles",               "actions": ["view", "create", "edit", "delete"]},
    {"key": "settings",      "label": "Settings",            "actions": ["view", "manage"]},
]

ACTION_LABELS: dict[str, str] = {
    "view": "View", "create": "Create", "edit": "Edit", "delete": "Delete",
    "assign": "Assign", "transfer": "Transfer", "block": "Block",
    "checkin": "Check in", "checkout": "Check out",
    "approve": "Approve", "refund": "Refund", "waive": "Waive",
    "update": "Update", "close": "Close", "publish": "Publish",
    "mark": "Mark", "manage": "Manage", "reply": "Reply",
    "deactivate": "Deactivate", "export": "Export",
}

ALL_PERMISSIONS: list[str] = [
    f"{m['key']}.{a}" for m in PERMISSION_MODULES for a in m["actions"]
]

# Master-admin permissions are a separate namespace. A tenant role can never
# hold one, and a master admin never holds a tenant permission.
MASTER_PERMISSIONS: list[str] = [
    "master.dashboard",
    "master.organizations",
    "master.organizations.create",
    "master.organizations.edit",
    "master.subscriptions",
    "master.usage",
    "master.audit",
    "master.impersonate",
    "master.settings",
]


def label_for(code: str) -> str:
    module, _, action = code.partition(".")
    mod = next((m for m in PERMISSION_MODULES if m["key"] == module), None)
    if mod is None:
        return code
    return f"{ACTION_LABELS.get(action, action.title())} {mod['label'].lower()}"


def catalog_rows() -> list[dict]:
    """Flat rows for seeding the `permissions` table."""
    rows = [
        {"code": f"{m['key']}.{a}", "module": m["key"], "action": a,
         "label": f"{ACTION_LABELS.get(a, a.title())} {m['label'].lower()}", "is_master": False}
        for m in PERMISSION_MODULES for a in m["actions"]
    ]
    rows += [
        {"code": c, "module": "master", "action": c.split(".", 1)[1],
         "label": c.replace("master.", "Master: ").replace(".", " ").title(), "is_master": True}
        for c in MASTER_PERMISSIONS
    ]
    return rows
