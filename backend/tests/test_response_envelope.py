"""
Every endpoint must return the `ok()` / `paginated()` envelope.

The frontend's `unwrap()` is `response?.data ?? null`. An endpoint that returns
a bare dict therefore hands the page **null** - with a 200 status, no console
error and no failed request. The screen renders entirely from its fallbacks, so
it looks like the data is simply empty.

That is what happened to the owner's subscription screen: wallet zero, plan
blank, and "online payment is not set up" all at once, on an account where the
plan existed and the gateway had just verified. Four wrong readings from one
missing wrapper.

Checked by parsing rather than by calling, so it covers every route including
the ones no test exercises yet.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

ENDPOINTS = pathlib.Path(__file__).resolve().parent.parent / "app" / "api"

#: Returning a Response subclass directly is legitimate - a PDF or a redirect
#: is not JSON and has no envelope to carry.
RAW_RESPONSE_CALLS = {"Response", "FileResponse", "StreamingResponse",
                      "RedirectResponse", "HTMLResponse", "JSONResponse",
                      "PlainTextResponse"}
ENVELOPE_CALLS = {"ok", "paginated", "created", "no_content"}

#: Health checks are deliberately bare. Render reads them, not the app, and a
#: probe that has to dig into `.data` to find "ok" is a worse probe.
EXEMPT_MODULES = {"health.py"}


def _envelope_locals(func) -> set[str]:
    """
    Names assigned from an envelope call inside this function.

    `list_notifications` builds `payload = paginated(...)`, adds an extra key to
    it and then returns the variable. That is correctly enveloped, and a check
    that only looks at the return expression would call it a bug - which is how
    a useful test gets deleted for crying wolf.
    """
    names: set[str] = set()
    for stmt in ast.walk(func):
        if not isinstance(stmt, ast.Assign) or not isinstance(stmt.value, ast.Call):
            continue
        call = (getattr(stmt.value.func, "id", None)
                or getattr(stmt.value.func, "attr", None) or "")
        if call in ENVELOPE_CALLS:
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _endpoint_functions(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(isinstance(d, ast.Call)
               and getattr(d.func, "attr", "") in
               ("get", "post", "patch", "put", "delete")
               for d in node.decorator_list):
            yield node


def _module_files():
    return sorted(p for p in ENDPOINTS.rglob("*.py")
                  if p.name not in ("__init__.py",))


@pytest.mark.parametrize("path", _module_files(), ids=lambda p: p.name)
def test_endpoints_return_the_envelope(path: pathlib.Path):
    if path.name in EXEMPT_MODULES:
        pytest.skip(f"{path.name} is deliberately un-enveloped")

    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []

    for func in _endpoint_functions(tree):
        wrapped_locals = _envelope_locals(func)
        for stmt in ast.walk(func):
            if not isinstance(stmt, ast.Return) or stmt.value is None:
                continue
            value = stmt.value

            if isinstance(value, ast.Call):
                name = (getattr(value.func, "id", None)
                        or getattr(value.func, "attr", None) or "")
                if name in ENVELOPE_CALLS or name in RAW_RESPONSE_CALLS:
                    continue
                # a helper that itself returns an envelope - trust it
                if name.startswith("_"):
                    continue

            if isinstance(value, ast.Name) and value.id in wrapped_locals:
                continue

            if isinstance(value, (ast.Dict, ast.List, ast.Constant, ast.Name)):
                offenders.append(f"{func.name}() line {stmt.lineno}")

    assert not offenders, (
        f"{path.name}: these return a bare value, so unwrap() gives the page "
        f"null and it renders from its fallbacks with no error anywhere: "
        f"{offenders}")
