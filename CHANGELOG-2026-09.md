# September 2026 update

Twelve requests, all shipped. Backend: 329 tests pass (317 before + 12 new in
`backend/tests/test_pgdesk_updates.py`). One migration: `0013_staff_notice_menu_pay`.
**No new APK needed** - no new Capacitor plugin or Android permission. Ship with
`npm version patch` then `npm run build:update` (see HANDOVER §6).

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
