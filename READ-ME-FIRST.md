# Fix: the subscription page rendered entirely from its fallbacks

## What you saw

Wallet ₹0, plan "—", renews "—", next charge "—", and "Online payment is not
set up on this platform yet" — all at once, on an account whose plan is Starter
and whose gateway had just verified green.

Four wrong readings, one cause: **the whole response arrived as `null`.**

## Why

The frontend's `unwrap()` is `response?.data ?? null`. Every endpoint in this
app returns `ok(payload)`, which wraps as `{"success": true, "data": …}`.

Mine returned bare dicts. So `unwrap()` looked for `.data`, found nothing, and
handed the page null — with a 200 status, no console error and no failed
request. The screen then rendered from its own fallbacks, which is exactly what
"empty" looks like.

A 500 would have been easier to debug than this.

## The test

`test_response_envelope.py` parses every endpoint in `app/api` and asserts the
return goes through `ok()` or `paginated()`. Checked by parsing rather than
calling, so it covers routes no test exercises yet.

It took two attempts to make it honest. The first version flagged two of your
existing files wrongly:

- `health.py` returns bare JSON deliberately — Render reads it, not the app, and
  a probe that has to dig into `.data` to find "ok" is a worse probe. Now
  explicitly exempt.
- `list_notifications` does `payload = paginated(...)`, adds `unread_count`, then
  returns the variable. Correctly enveloped; my check only looked at the return
  expression. It now traces local assignment.

Verified: with a bare return put back it fails and names the function and line.

## Files

```
backend/app/api/v1/endpoints/platform_billing.py   8 returns wrapped
backend/app/api/v1/endpoints/master_coupons.py     11 returns wrapped
backend/tests/test_response_envelope.py            the new check
frontend/src/pages/org/PlatformBilling.jsx         reads the flattened list
frontend/src/pages/master/Coupons.jsx              reads the flattened list
```

List endpoints now return `ok([...])` to match `master.py`, rather than the
double-nested `ok({"data": [...]})` they had — so the two pages read
`history.data` instead of `history.data?.data`.

Copy over your repo, then from the repo root:

```powershell
git add .
git commit -m "fix: endpoints returned no response envelope"
git push origin main
```

No migration.

## After it deploys

Reload **My subscription** as the PG owner. You should see:

- Wallet balance ₹0 (correct — nothing topped up yet)
- Current plan **Starter**, ₹— / monthly
- Renews **23 Oct 2026**, 39 days left
- Next charge, and a **Pay by card or UPI** button that is enabled
- The "not set up" banner gone

If the banner is still there but the plan now shows, that is a different thing:
`gateway_available` is read straight from the saved settings, so it would mean
the enabled toggle is off in master admin.
