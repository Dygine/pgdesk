"""
Wildcard expansion, mirroring `src/lib/rbac.js`.

    "*"           -> every tenant permission
    "rooms.*"     -> every action on rooms
    "rooms.edit"  -> itself

Wildcards are accepted on input for convenience; they are expanded to concrete
codes before anything is written, so the database never stores a wildcard.
"""
from collections.abc import Iterable

from app.permissions.catalog import ALL_PERMISSIONS, MASTER_PERMISSIONS

WILDCARD = "*"


def expand(granted: Iterable[str], *, include_master: bool = False) -> set[str]:
    granted = list(granted or [])
    universe = list(ALL_PERMISSIONS) + (list(MASTER_PERMISSIONS) if include_master else [])

    if WILDCARD in granted:
        return set(universe)

    out: set[str] = set()
    for perm in granted:
        if perm.endswith(".*"):
            prefix = f"{perm[:-1]}"          # "rooms.*" -> "rooms."
            out.update(p for p in universe if p.startswith(prefix))
        else:
            out.add(perm)
    return out


def can(granted: Iterable[str], permission: str | list[str]) -> bool:
    """A list means OR, matching the frontend's `can()`."""
    held = expand(granted, include_master=True)
    if isinstance(permission, list):
        return any(p in held for p in permission)
    return permission in held


def unknown_permissions(codes: Iterable[str]) -> list[str]:
    """Validation helper: which of these are not in the catalogue?"""
    known = set(ALL_PERMISSIONS) | set(MASTER_PERMISSIONS)
    bad = []
    for c in codes:
        if c == WILDCARD or c.endswith(".*"):
            continue
        if c not in known:
            bad.append(c)
    return bad
