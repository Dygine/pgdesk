# September 2026 update

Twelve requests, all shipped, plus one sign-in fix (below). Backend: 332 tests pass
(317 before + 12 in `backend/tests/test_pgdesk_updates.py` + 3 in `test_auth_session.py`
+ 8 in `test_resident_documents.py`) - 340 in all. One migration: `0013_staff_notice_menu_pay`.
**One new APK, once** - it now opens the live website, so everything after
ships with `git push` alone (see the last section and HANDOVER §6).

| # | Request | What changed |
|---|---|---|
| 1 | Notification panel went off the side of the screen in the app | The bell panel was `absolute right-0`, 22rem wide, anchored to the bell - which on a phone is not at the screen edge. It is now rendered into `<body>` and positioned from the bell: a full-width sheet with 8px margins on phones, a dropdown from `sm` up. Tapping a notification now opens the page it is about (it only marked it read before). |
| 2 | Floor plan under Overview | `navConfig.js`: Overview = Dashboard, Floor plan, Reports. |
| 3 | Enquiries before All residents | Residents group reordered. |
| 4 | Check-in after All residents | Residents group = Enquiries, All residents, Check-in, Room transfer, Checkout. |
| 5 | Residents can give checkout notice | New `checkout_notices` table. Resident app: **Moving out** screen - pick the last day (defaults to the notice period), optional reason, withdraw any time before the date. Status becomes NOTICE (keeps bed, QR, rent). Office: notices list on **Checkout** with days left, short-notice flag vs deposit, Acknowledge / Check out / Cancel, and "Record a notice" for someone who told the desk. Checkout closes the notice. Notice period is a setting (Settings → Billing, default 30). Short notice is allowed but flagged. |
| 6 | Razorpay per PG, or UPI/QR/bank with mandatory UTR | Settings → **Payments**. Razorpay key secret + webhook secret are encrypted and write-only (same rule as the Brevo key). Resident app: **Pay now** on each unpaid invoice. Razorpay: server creates the order, verifies the HMAC signature, records VERIFIED; webhook covers a phone that dies mid-payment; completion is idempotent. UPI: app draws a UPI QR with amount + invoice number filled in, "Open UPI app" link, optional photo of the PG's printed QR. Bank: account details with copy buttons. UPI/bank need the UTR (UPI: exactly 12 digits; bank: 6–22 letters/digits), duplicates refused, payment stays PENDING until verified under Payments. Payments list shows who put each payment in (Desk / Resident / Razorpay). |
| 7 | Show the gate QR on Gate scan | Your understanding was right. The gate QR (residents scan it) lived only in Branches → Gate setup. Gate scan now shows it per branch, with readiness checks and a full-screen mode for a tablet at the gate. |
| 8 | Simple accounts / P&L | New **Accounts (P&L)** page under Finance (`reports.view`). Cash basis: verified payments in minus expenses out (salaries included). Deposits, tax, assets bought and stock added are shown but kept out of profit. Billed vs collected per income type, 6-month trend, CSV export. |
| 9 | Daily menu, weekly repeat, keep one week | New `food_week_menus`: a Mon–Sun menu that repeats every week. A date-specific menu is now a one-day **special** that overrides it; specials older than 7 days are deleted automatically (on save, and in the daily `expire_subscriptions.py` run). **Meals & timings**: switch meals on/off, rename them ("Evening tea"), set serving times. Residents see the effective menu with times and specials. |
| 10 | Staff and Users were the same page | They were - `Staff.jsx` was a one-line re-export of Users. Staff is now a real workforce list (`staff_members`): cook, cleaner, guard… no login needed; role, shift, salary, joining date, ID proof, emergency contact, optional link to a login. **Pay salary** records a Salary expense for that month (twice for the same month is refused), so it flows into Expenses and the P&L. Users is relabelled **Users & logins**. |
| 11 | Owner's query never reached the resident | It did reach their "Ask the PG" page, but: no notification was sent, the message was saved with the *resident's own name* as author, and the modal read like logging a note. Now the office's name is the author, the resident is notified (tap opens the question), it shows "From the office · Needs your reply", and statuses read "Needs a reply" / "Waiting on resident". Staff are also notified when a resident asks or replies. The Visitors and Gate pass links now open their own tab. |
| 12 | Toggle switches looked broken everywhere | The knob was absolutely positioned with no `left`; inside a `<button>` the Android WebView centres content, so "off" sat mid-track and "on" hung past the edge. Rebuilt as a flex track with a transform-only knob, focus ring, disabled state, `sm`/`md` sizes. One component, so every toggle is fixed. |

## New endpoints

Owner/staff: `GET/POST /staff`, `GET/PATCH /staff/{id}`, `POST /staff/{id}/salary`,
`GET /checkout-notices`, `POST /checkout-notices/{id}/acknowledge|cancel`,
`POST /residents/{id}/checkout-notice`, `GET/PUT /payment-settings`,
`POST /payment-settings/test-razorpay`, `GET /accounts/pnl`, `GET /accounts/pnl/export`,
`GET /scan/gate-codes`, `GET/PUT /food/week`, `GET/PUT /food/schedule`,
`GET /food/menus/effective`, `DELETE /food/menus/{id}`.

Resident: `GET/POST /me/checkout-notice`, `POST /me/checkout-notice/withdraw`,
`GET /me/payments/options`, `POST /me/payments/manual`,
`POST /me/payments/razorpay/order`, `POST /me/payments/razorpay/verify`.

Public (Razorpay only, HMAC-checked): `POST /payments/razorpay/webhook/{organization_id}`.

No new permission codes - everything reuses the existing catalogue, so the
JS/Python permission-parity test is untouched.

## Fix: the app asked people to sign in again after a deploy

Reported right after pushing this update. Not caused by the update - a
pre-existing bug in how the app restores its session, which a deploy (or the
free Render server waking up) triggers:

1. **Any error deleted the saved login.** `refreshAccessToken()` in
   `frontend/src/services/api/client.js` treated every failed refresh - a 502
   while Render swaps in a new deploy, a 500 while the database wakes - as "this
   token is dead" and removed it from the phone. Now only a real 401 from the
   server removes it; everything else keeps it.
2. **"Can't reach the server" looked like "not signed in".** The app showed the
   sign-in form. Now it shows *Connecting to PGDesk…* and retries by itself
   (2s, 4s, 8s, then every 15s, and at once when signal returns or the app is
   reopened). It only goes to the sign-in form if the server actually says the
   login is invalid.
3. **A lost reply looked like theft to the server.** The app sends its token,
   the server rotates it, the reply never arrives (slow wake-up, dropped
   signal). The app asks again with the old token and the server signed out
   every device. `AuthService.rotate_refresh_token` now treats that as a retry
   when the token was rotated within 10 minutes and its replacement was never
   used. Theft detection is unchanged otherwise: once the replacement has been
   used, or after 10 minutes, a replay still signs out every session, and the
   undelivered replacement is retired so it can never be used.

Ships with `git push`; phones get it through the new APK described below.

## The app now opens the live website

Reported with screenshots: the website had every change, the APK showed old
screens. Why: the APK carried its own copy of the screens, and its self-update
looked for new versions at a relative `/updates/version.json` - inside the app,
that is the app's own files - so no installed app ever received an update.

Now `capacitor.config.json` has `server.url: https://pgdesk.dygine.com`: the app
opens the website itself. A deploy updates the browser and the app together.

- Removed `@capgo/capacitor-updater`, `scripts/publish-update.mjs` and the
  `build:update` / `publish:update` scripts.
- `src/lib/liveUpdate.js` + `UpdateBanner.jsx`: an already-open screen notices a
  newer deploy and offers "Reload" (never forces it).
- `public/offline.html` (`server.errorPath`): shown with no internet, retries
  when the connection returns.
- `scripts/check-android-env.mjs` refuses to build unless `server.url` is https.

**Needs one new APK** (the old one cannot learn the new address by itself).
After that: `git push` is the whole release process.

## Scanned ID documents (up to 3 per resident, 5 KB each)

- New table `resident_documents` (migration `0014_resident_documents`), images
  stored as bytes. The 5 KB (5,120-byte) limit is enforced by the app, the API
  (`ResidentDocumentService`) and two CHECK constraints in the database.
- **Scan with camera**: crop to the document, grey with stretched contrast, then
  the largest size that fits under 5 KB at a readable quality (WebP where
  possible) - `frontend/src/lib/docScan.js`.
- **Upload image**: accepted only if already under 5 KB (JPEG, PNG or WebP, checked
  by content, not by name); a larger file is refused with its size and can be
  shrunk like a scan.
- In the **Add resident** form (saved once the resident exists) and on the
  profile's **Documents** tab (add later, view, delete). The old per-number KYC
  card there is now labelled "ID numbers" so the two are not confused.
- Images only go to roles with `customers.kyc_view`; others see that a document
  exists. Uploads and deletions are in the audit log, never the image.
- Works in the current APK: the camera opens through the normal file picker,
  which the app already supports. Ships with `git push`.
