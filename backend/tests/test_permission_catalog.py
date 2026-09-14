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


def test_every_permission_used_in_an_endpoint_exists():
    """
    A `require("...")` string that is not in the catalogue can never be held by
    anyone, so the endpoint 403s every caller - including the owner - and the
    matching nav item silently disappears from the sidebar.

    That is exactly what happened with the platform billing screen: guarded on
    `org.settings.manage`, which looks plausible and does not exist. The feature
    was unreachable in every layer at once, with no error anywhere naming why.

    Two things this check is careful about, because a test that cries wolf on
    existing code gets deleted rather than fixed:

    - Docstrings are stripped first. `dependencies.py` documents `require()`
      with an illustrative `payments.approve`, which is prose, not a guard.
    - `require(a, b)` means *a or b*, so it only fails when **every**
      alternative is unknown. `require("users.delete", "users.deactivate")` is
      fine - the second one exists, so the endpoint is reachable.
    """
    import ast
    import pathlib

    from app.permissions.catalog import ALL_PERMISSIONS

    known = set(ALL_PERMISSIONS) | {"*"}
    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    broken: dict[str, str] = {}

    for path in root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                      # pragma: no cover
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)

            if name == "require":
                codes = [a.value for a in node.args
                         if isinstance(a, ast.Constant) and isinstance(a.value, str)]
                # OR semantics: broken only if not one of them is real.
                if codes and not any(c in known for c in codes):
                    broken[f"{path.name}: require({codes})"] = "none exist"

            elif name == "to_permission_holders" and len(node.args) >= 2:
                arg = node.args[1]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value not in known:
                        broken[f"{path.name}: to_permission_holders({arg.value!r})"] = (
                            "does not exist, so nobody is ever notified")

    assert not broken, (
        "permission strings that can never be granted - the endpoint 403s "
        f"everyone and the nav item vanishes: {broken}")
