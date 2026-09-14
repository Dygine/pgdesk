# Fix: "My subscription" was invisible — and the whitespace fix, rolled in

## Why the menu item was missing

I guarded the whole owner-facing feature on a permission that **does not exist**.

The catalogue has `settings.manage`. I wrote `org.settings.manage` — plausible,
consistent-looking, and completely made up. Because no role can hold it:

- the sidebar filtered the item out
- the route guard blocked the page
- every API endpoint would have 403'd the owner
- `to_permission_holders(...)` notified nobody

Four layers failing at once, none of them producing an error that named the
cause. The feature was unreachable and looked simply absent.

This corrects all thirteen occurrences across six files.

## Also in here: the whitespace patch

If you have not applied `dygine-credentials-fix.zip` yet, don't — it is included
here. Credentials are stripped on save and again at point of use, and gateway
errors are readable instead of dumping an HTML error page into a toast.

## Two tests

`test_every_permission_used_in_an_endpoint_exists` parses every `require(...)`
and `to_permission_holders(...)` in the app and checks the strings against the
catalogue. It is careful about two things, because a test that cries wolf on
existing code gets deleted rather than fixed:

- it parses the AST, so the illustrative `payments.approve` in a `dependencies.py`
  docstring is not mistaken for a guard
- `require(a, b)` means *a or b*, so it fails only when **every** alternative is
  unknown — your existing `require("users.delete", "users.deactivate")` is fine,
  the second one exists

Verified: with `org.settings.manage` put back it fails and names the file and the
string; with the fix it passes. 103 tests pass overall.

`test_pasted_credentials_are_stripped` covers the trailing-newline case.

## Eight files

```
backend/app/api/v1/endpoints/platform_billing.py    permission
backend/app/api/v1/endpoints/master_coupons.py      permission
backend/app/services/platform_billing_service.py    permission
backend/app/services/platform_settings_service.py   strip on save
backend/app/services/dygine_client.py               strip on use, better errors
backend/tests/test_permission_catalog.py            the new check
backend/tests/test_platform_settings.py             whitespace test
frontend/src/nav/navConfig.js                       permission
frontend/src/routes/index.jsx                       permission
frontend/src/pages/org/PlatformBilling.jsx          permission
```

Copy over your repo, then from the repo root:

```powershell
git add .
git commit -m "fix: platform billing was guarded on a permission that does not exist"
git push origin main
```

No migration.

## After it deploys

Sign in as the PG owner. **My subscription** appears in the sidebar under
Admin & setup, above Settings.

Open it. You should see the wallet balance at zero, the Starter plan, days
remaining, and what the next charge would be. That is the first end-to-end proof
that PGGuru is talking to Dygine as an owner rather than as you.

If the item is still missing, the owner's role does not hold `settings.manage` —
check Roles & permissions. A system Owner role holds `*` and will always see it.
