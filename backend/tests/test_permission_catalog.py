"""
The parity test.

The backend catalogue and the React app's `src/data/permissions.js` must contain
exactly the same permission codes. If they drift, the UI renders a control the
API will refuse - a bug that is invisible until a user hits it. This test parses
the JavaScript and compares the two lists directly.
"""
import json
import re
from pathlib import Path

import pytest

from app.permissions.catalog import ALL_PERMISSIONS, MASTER_PERMISSIONS
from app.permissions.engine import can, expand, unknown_permissions

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src" / "data" / "permissions.js"


def _parse_frontend() -> tuple[set[str], set[str]]:
    src = FRONTEND.read_text(encoding="utf-8")

    modules = re.search(r"PERMISSION_MODULES\s*=\s*\[(.*?)\n\]", src, re.S).group(1)
    tenant = set()
    for key, actions in re.findall(r"key:\s*'([\w]+)'.*?actions:\s*\[([^\]]*)\]", modules, re.S):
        for action in re.findall(r"'([\w]+)'", actions):
            tenant.add(f"{key}.{action}")

    master_block = re.search(r"MASTER_PERMISSIONS\s*=\s*\[(.*?)\]", src, re.S).group(1)
    master = set(re.findall(r"'([\w.]+)'", master_block))
    return tenant, master


@pytest.mark.skipif(not FRONTEND.exists(), reason="frontend source not present")
def test_tenant_permissions_match_frontend():
    tenant, _ = _parse_frontend()
    backend = set(ALL_PERMISSIONS)
    assert backend == tenant, (
        f"only in backend: {sorted(backend - tenant)} | only in frontend: {sorted(tenant - backend)}"
    )


@pytest.mark.skipif(not FRONTEND.exists(), reason="frontend source not present")
def test_master_permissions_match_frontend():
    _, master = _parse_frontend()
    assert set(MASTER_PERMISSIONS) == master


def test_no_duplicate_codes():
    assert len(ALL_PERMISSIONS) == len(set(ALL_PERMISSIONS))


def test_wildcard_expands_to_everything():
    assert expand(["*"]) == set(ALL_PERMISSIONS)


def test_module_wildcard_expands_to_that_module_only():
    result = expand(["rooms.*"])
    assert result == {p for p in ALL_PERMISSIONS if p.startswith("rooms.")}
    assert "beds.view" not in result


def test_module_wildcard_does_not_leak_across_prefixes():
    """'roles.*' must not pick up 'rooms.*' - both start with 'ro'."""
    result = expand(["roles.*"])
    assert all(p.startswith("roles.") for p in result)


def test_can_accepts_a_list_as_or():
    granted = ["payments.view"]
    assert can(granted, ["payments.approve", "payments.view"]) is True
    assert can(granted, ["payments.approve", "payments.refund"]) is False


def test_unknown_permissions_are_reported():
    assert unknown_permissions(["rooms.view", "rooms.teleport"]) == ["rooms.teleport"]
    assert unknown_permissions(["*", "rooms.*"]) == []
