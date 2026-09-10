# PGDesk — multi-tenant PG & hostel management

A SaaS platform for Indian paying-guest and hostel operators. Four portals,
one responsive React application, a FastAPI backend, PostgreSQL underneath.

**One deploy updates everything.** The website and the Android app run the
same screens: the APK opens https://pgdesk.dygine.com inside the app (see
[The Android app](#the-android-app)), so a `git push` updates both.

**The frontend talks to the API for everything.** There is no browser demo store:
authentication, residents, beds, billing, operations, support and reporting are
all served by the backend and enforced there. If the API is not running, the app
does not work — which is correct for a product whose security model lives on the
server.

---

## Architecture

```
React 18 + Vite  ──HTTP──▶  FastAPI  ──▶  SQLAlchemy 2.0  ──▶  PostgreSQL 16
 (browser + APK)             (ASGI)          (ORM)             (54 tables)
```

- **230 API routes** across 16 endpoint modules under `/api/v1`
- **14 Alembic migrations**, verified to run from an empty database
- **340 backend tests**

---

## What changed in September 2026

Full detail in [`CHANGELOG-2026-09.md`](CHANGELOG-2026-09.md); operations notes in
[`HANDOVER.md`](HANDOVER.md) §6, §8 and §15.

- **Staff** is a real workforce list (cooks, cleaners, guards - no login needed)
  with salaries that post to Expenses. **Users & logins** is the separate login list.
- **Checkout notice** - residents give notice from the app; the office sees days
  left and short notice on the Checkout screen.
- **Resident payments** - Pay now on every invoice: Razorpay (each PG's own keys,
  stored encrypted), or UPI/bank transfer with a mandatory UTR that the office verifies.
- **Accounts (P&L)** - cash-basis profit and loss; deposits and tax kept out of profit.
- **Food** - a weekly menu that repeats, one-day specials (auto-deleted after a
  week), and the PG's own meal names and timings.
- **Query centre** - a query the office sends reaches the resident, with a notification.
- **Gate scan** shows the branch gate QR for residents to scan.
- **Scanned ID documents** - up to 3 per resident, 5 KB each (see below).
- **Sign-in fix** - a server restart or deploy no longer signs anyone out.
- **The Android app opens the live website** - no more stale screens in the APK.
- UI fixes: notification panel on phones, every toggle switch, sidebar order.

---

## The Android app

The APK is a thin shell: `frontend/capacitor.config.json` sets `server.url` to
`https://pgdesk.dygine.com`, so the app shows the live website, while the
camera, GPS, notifications and the saved login stay native.

| You change | What to do |
|---|---|
| Screens, features, fixes, API | `git push` - Render deploys, the app shows it on next open |
| A new native plugin or Android permission, the icon or name, the website address | Build and share a new APK (HANDOVER §5) |

An already-open screen offers "A new version of PGDesk is ready - Reload". With
no internet the app shows `public/offline.html` and retries by itself.

---

## Scanned ID documents

Each resident can have **up to 3 document images** (Aadhaar, PAN, passport,
driving licence, voter ID, other), **each at most 5 KB (5,120 bytes)**:

- **Scan with camera** - the phone camera opens; the photo is cropped to the
  document, turned grey with the contrast stretched, and shrunk until it fits.
- **Upload image** - accepted only if it is already under 5 KB. A larger file is
  refused with its size, with an option to shrink it the same way as a scan.
- Add them in the Add resident form, or later from the resident's Documents tab.

The limit is enforced three times: in the app, by the API, and by a CHECK
constraint in the database. Images are stored in PostgreSQL (`resident_documents`);
at 15 KB per resident that is about 15 MB per thousand residents. Only roles with
`customers.kyc_view` can see the images. At 5 KB, names and ID numbers stay
readable; small print (such as the address on the back of an Aadhaar) usually
does not. The limit is `DOCUMENT_MAX_BYTES` in `backend/app/models/customer.py`
and `DOC_MAX_BYTES` in `frontend/src/lib/docScan.js` - change both, plus the
CHECK in a migration.

### The two rules everything else rests on

1. **`organization_id` is never read from the request.** Not from the body, the
   path, or a query parameter. It comes from the authenticated identity only,
   via `CurrentScope`. A client cannot ask for another tenant's data because
   there is nowhere to put the request.

2. **A row belonging to another tenant answers 404, not 403.** "Forbidden"
   confirms the row exists, which turns any id endpoint into an existence
   oracle. See `app/core/exceptions.py:TenantIsolationError`.

Branch scoping is a second, independent filter. `CurrentScope.all_branches` is a
display hint, not a bypass — it is expanded to a concrete branch list at request
start, and `owns_branch()` checks membership in that list. Treating the flag as a
shortcut would let an owner satisfy the branch guard for an arbitrary id,
including one from another tenant.

---

## Running it

### 1. PostgreSQL

```bash
createdb pgdesk
createdb pgdesk_test          # the suite runs against a separate database
```

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then edit — see "Configuration"
alembic upgrade head
python seed.py                # development accounts and sample data

uvicorn app.main:app --reload # http://localhost:8000/docs
```

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev                   # http://localhost:5173
```

---

## Configuration

Every setting is read from the environment; nothing secret is in the source tree.
`.env` is gitignored — commit `.env.example` only.

`app/core/config.py:assert_production_safe()` runs at startup and **refuses to
boot** when `ENVIRONMENT=production` and any of these are wrong:

| Setting | Production requirement | Why |
|---|---|---|
| `SECRET_KEY` | >=32 chars, not a default | Signs every access token |
| `CORS_ORIGINS` | Exact origins, never `*` | Credentials ride on every request |
| `DEBUG` | `false` | Debug responses can carry internals |
| `REFRESH_COOKIE_SECURE` | `true` | Otherwise the session cookie crosses plaintext |
| `EXPOSE_REFRESH_TOKEN_IN_BODY` | `false` | A body value is readable by injected script |

Set `REFRESH_COOKIE_SECURE=false` **only** for local http development, where a
Secure cookie would never be sent at all.

---

## Session handling

The refresh token is an **HttpOnly, Secure, SameSite cookie** scoped to
`/api/v1/auth`. It is never in a response body and never reachable from
JavaScript, so an XSS cannot steal the long-lived credential. Scoping it to the
auth path means it is not attached to the other ~115 API calls — a token that is
not sent cannot leak from a log or a proxy.

The **access token lives in memory** in a module-scoped variable in
`services/api/client.js` — not localStorage, not sessionStorage. On reload the
client calls `/auth/refresh`, which the cookie authenticates, so the session
survives without anything durable on disk.

**CSRF.** A cookie is attached by the browser whether or not the page asked for
it, so cookie-authenticated calls require the `X-PGDesk-Auth` header as a second
factor. A cross-site `<form>` post cannot set a custom header, and a
cross-origin `fetch` that sets one must pass a preflight that is only answered
for the origins in `CORS_ORIGINS`.

Refresh tokens are **single-use**: each refresh rotates the pair, and replaying a
spent token revokes the whole family on the assumption that a copy is in
circulation.

**Brute force.** Sign-in failures are persisted (`login_attempts`) and counted in
sliding windows — 5 per identifier and 20 per IP over 15 minutes. Past either
threshold the endpoint answers 429 with `Retry-After`. Counting in the database
rather than in memory matters: a lockout that resets on worker restart is not a
lockout, and multiple workers would each give an attacker a fresh budget. A
correct password clears that identifier's failures.

---

## Portals and roles

| Portal | Who | Route |
|---|---|---|
| Master | Platform operator | `/master` |
| Organisation | PG owner, manager, accountant, receptionist, security, custom roles | `/app` |
| Resident | Tenants | `/me` |

RBAC is **fully dynamic**. Permissions come from a catalogue
(`app/permissions/catalog.py`); roles are tenant-owned rows holding any subset.
The named roles above are seed data, not code — a PG that invents "Night Warden"
gets identical enforcement. Permissions are resolved per request rather than
baked into the JWT, so granting or revoking one takes effect on the **next
request**, not the next login.

Every protected endpoint carries a `require("...")` guard. Frontend route guards
and hidden buttons are presentation only.

---

## The gate

Two directions, both live, writing to the same `gate_logs` table and told apart
by `source`. Neither replaces the other.

| Flow | Who scans | `source` | Needs |
|---|---|---|---|
| Guard scans resident | staff, `POST /scan` | `qr` | the resident's card or phone screen |
| Resident scans gate | resident, `POST /me/scan` | `self` | a smartphone, GPS, and the gate poster |

The second one exists because residents ask for it and it removes a queue at the
gate. It is also the harder of the two to get right, because it inverts who
creates the record: with a guard scanning, the writer is a trusted employee;
with self check-in, the writer is the person who benefits from the record being
wrong.

Two independent checks, and the point is that neither is sufficient alone:

1. **The gate QR.** Printed and stuck on a wall, so it leaks by design - a
   photograph is enough. On its own it proves nothing about where anyone is.
2. **The geofence.** The phone's position, compared against the branch's
   coordinates. A mock-location app can put a phone anywhere, so on its own this
   proves nothing either.

Together an absent resident needs a photograph of a code they could only get by
being there, plus a spoofing app, plus a willingness to leave a false position
in an append-only log. That is a deterrent proportionate to a hostel attendance
register, not proof of presence, and the code says so rather than implying
otherwise. Every self check-in stores `latitude`, `longitude`, `accuracy_m` and
`distance_m` - **including the refused ones** - so a pattern of impossible
positions is reviewable after the fact.

Where attendance carries real consequences, the guard flow and a biometric
device are the answer, and the first of those is already here.

### Setup

`Branches → Gate`, which needs `branches.edit`. Stand at the gate, tap **Use my
current location**, set a radius, switch self check-in on. A gate code is issued
on save; print the poster from the same screen. **Reissue** kills every printed
copy immediately, which is the response to a code believed to be circulating.

The default radius is 150 m. Phone GPS beside a building in an Indian city is
routinely 20-50 m out, and a fence that does not absorb that refuses residents
who really are standing at the gate - a support call nobody traces back to a
number typed once during setup. A reading worse than 100 m accuracy is refused
outright rather than believed, because accepting it would make any radius
decorative.

### QR payload

    PGD1:R:<token>    a resident's card
    PGD1:G:<token>    a gate's code

Defined once in `app/utils/qr_payload.py` and mirrored in `src/lib/qr.js`. The
prefix lets a camera drop the UPI sticker next to the gate before a request is
made; without it every foreign code becomes an indistinguishable "not
recognised" and guards learn to ignore the message. Bare tokens still parse, so
cards printed before this format and hardware barcode guns keep working.

### Scanning

Android uses Google's ML Kit through `@capacitor-mlkit/barcode-scanning`; the
browser falls back to `getUserMedia` plus jsQR. **A browser camera needs https**
- over plain http `getUserMedia` does not exist, and that is the most common
cause of a scanner that appears broken.

## Signing up

Three ways in, and they are genuinely different things:

| Who | Route | What they get |
|---|---|---|
| PG owner | `/signup` | An organisation, an owner login, a 30-day trial |
| Looking for a PG | `/signup` → `/find-pg` | A verified email and the ability to enquire. **No account** |
| Existing resident/staff | `/login` | Created by their PG, not self-service |

The middle one surprises people, so the screen says it plainly. A person hunting
for a PG belongs to no organisation, and every login here is scoped to one -
giving them a session would mean a third principal kind threaded through the
token tables and every isolation rule built on them, for someone whose whole
interaction is "I saw your listing, call me". They become a resident through the
ordinary check-in flow when they move in.

Email is proved by a 6-digit code before anything is created. Without that,
signup is a way to register organisations under other people's addresses.

### The trial, and what happens after

    TRIAL/ACTIVE  --- end date passed --->  EXPIRED   (grace period starts)
    EXPIRED       --- grace passed   --->  SUSPENDED

Run `python expire_subscriptions.py` daily from cron. `--dry-run` reports
without writing. It is idempotent, so a retry after a failed deploy changes
nothing.

**Suspension freezes writes, not reads.** `assert_operational` guards the paths
that create records, not the ones that read them, so a suspended PG's staff can
still open the app and see everything - they just cannot add a resident or raise
an invoice. Residents are unaffected entirely.

That asymmetry is deliberate. Two hundred residents did not miss the payment,
and taking their rent history and gate check-in away over their landlord's
billing problem turns a renewal conversation into a support crisis.

## Public listings

Off by default, per branch, under **Branches → Listing**. What becomes public:
name, area, starting rent, amenities, and a phone number the owner chooses.

**Vacancy is published as a band, never a count.** "a few beds", not "4 beds". A
number answers the seeker's question and also hands anyone sampling the API
weekly a complete occupancy curve for every rival in the city - which is
commercially sensitive in a way that ticking "list my PG" is not consent for.

The public listing payload is written out field by field in `PublicService`
rather than serialised from the model, so a column added to `branches` next year
cannot reach a public page by being caught in a loop.

## Mail

Two transports, chosen under **Master → Platform settings → Email**. Both stay,
because they fail in different places.

| | Port | Works where |
|---|---|---|
| **Brevo** (recommended) | 443 (https) | everywhere |
| **SMTP** | 587 / 465 | your own VPS, paid managed hosting |

Managed hosts routinely block outbound SMTP on free plans — Render closed 25,
465 and 587 to free web services in September 2025 — so a perfectly correct
Gmail configuration fails there with `Network is unreachable` and nothing about
the message points at the host. An HTTP provider posts to 443, which is never
blocked because blocking it would break the platform itself.

SMTP is kept for anyone self-hosting who wants no third party in the path.

Credentials come from the environment first, then the database, for both. The
SMTP password and the Brevo key are encrypted at rest and have no read path in
the API: the settings response reports whether one is stored, never what it is.

**Send test** proves delivery, which is a different claim from "saved". A wrong
port, an unverified Brevo sender, or a Gmail account password where an app
password was needed all save perfectly and deliver nothing.


Configured under **Master → Platform settings → Mail server**, or from the
environment, which wins when set. The password is encrypted at rest and has no
read path in the API - the settings response reports whether one is stored, not
what it is.

There is a **Send test** button because "saved" and "delivers" are different
claims. A wrong port, or a Gmail account password where an app password was
needed, both save perfectly and send nothing.

## Modules

Branches, buildings, floors, rooms, beds - residents, KYC numbers and scanned ID
documents, check-in, bed assignment, transfer, checkout notices and checkout, QR
- invoices, rent generation, payments with a verify/refund state machine,
resident payments (Razorpay, UPI, bank transfer) - accounts (profit and loss) -
attendance, gate scan with the gate QR, visitors, gate passes - food: weekly
menu, specials, meal timings and meal attendance - laundry slots and bookings -
complaints, support queries in both directions - staff and salaries, users,
roles, permissions - expenses, inventory, assets - reports and CSV export -
notifications, announcements - audit log - organisation and platform settings -
subscriptions, plan limits and usage.

---

## Testing

```bash
cd backend
pytest                                    # the whole suite
pytest tests/test_concurrency.py          # threaded race tests
pytest tests/test_isolation_matrix.py     # tenant + branch isolation
pytest tests/test_rbac_matrix.py          # the permission grid
```

| Suite | What it proves |
|---|---|
| `test_migrations.py` | Migrations run from empty and match the models column-for-column, including nullability |
| `test_tenant_isolation.py` | The scope and repository layer |
| `test_isolation_matrix.py` | Every major resource, list/detail/mutation, tenant **and** branch |
| `test_rbac_matrix.py` | Five roles against the endpoint grid, both grant and deny |
| `test_concurrency.py` | Real threads: bed assignment, laundry capacity, stock |
| `test_workflows.py` | Check-in, transfer, checkout, payment approval, visitor, laundry, complaint |
| `test_security_hardening.py` | Enumeration, brute force, session revocation, cookie flags, disclosure, config |
| `test_check_in.py` | Atomicity, conflicts, validation |
| `test_self_checkin.py` | The geofence maths, the QR payload format, and every self check-in refusal - out of range, weak GPS, missing position, wrong code, wrong branch, another tenant's gate |

The concurrency tests use real connections and real threads with a barrier, so
they contend genuinely. They were verified by removing the `SELECT ... FOR
UPDATE` locks and confirming they fail, then restoring the locks.

Frontend:

```bash
cd frontend
npm run build      # also serves as the import/static check
npm run smoke
```

---

## Development seed data

`python seed.py` creates sample organisations, staff and residents. It **refuses
to run when `ENVIRONMENT=production`**.

The sign-in screen can offer these accounts as one-click logins, gated behind
`VITE_SHOW_SEED_ACCOUNTS=true`. Unset — the default — the credentials are not
merely hidden but **absent from the built bundle**, verified by grepping `dist/`.
Never set it in production: these are working credentials.

---

## Deployment

| Piece | Production form |
|---|---|
| Frontend | `npm run build` -> static files on any CDN or web server (Render static site `pgdesk`) |
| Android app | APK that opens the live site (`server.url`); rebuilt only for native changes |
| Backend | `uvicorn app.main:app` behind a process manager, multiple workers |
| Database | Managed PostgreSQL 16, migrations applied by `alembic upgrade head` |
| Secrets | Environment variables from the platform's secret store, never files in the image |

Run `alembic upgrade head` as a release step before the new code serves traffic.
Never modify schema outside a migration — `test_migrations.py` will catch drift.

---

## Known limitations

- **Email, SMS and WhatsApp are not wired.** The architecture is in place and the
  master settings screen reports each channel as configured or not, based on
  whether provider credentials exist in the environment. Nothing ever claims to
  have sent a message it did not send.
- **Scanned documents are small by design.** Up to 3 images per resident at
  5 KB each, stored in the database. Anything needing full-resolution scans would
  need object storage (S3, GCS) plus signed-URL access control.
- **The app needs internet.** It opens the live website; with no connection it
  shows an offline page and retries.
- **No frontend unit-test framework.** The build is the static check, plus the
  smoke scripts. Security-critical logic is on the server and covered there; a
  component suite is worth adding as the UI grows.
- **Impersonation is deliberately unimplemented.** `master.impersonate` exists as
  a permission but has no endpoint, and the client refuses to fake it locally —
  that would be a second, unauthenticated route into a tenant.
