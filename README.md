# PGDesk — multi-tenant PG & hostel management

A SaaS platform for Indian paying-guest and hostel operators. Four portals,
one responsive React application, a FastAPI backend, PostgreSQL underneath.

**The frontend talks to the API for everything.** There is no browser demo store:
authentication, residents, beds, billing, operations, support and reporting are
all served by the backend and enforced there. If the API is not running, the app
does not work — which is correct for a product whose security model lives on the
server.

---

## Architecture

```
React 18 + Vite  ──HTTP──▶  FastAPI  ──▶  SQLAlchemy 2.0  ──▶  PostgreSQL 16
   (browser)                 (ASGI)          (ORM)             (43 tables)
```

- **120 API routes** across 13 endpoint modules under `/api/v1`
- **7 Alembic migrations**, verified to run from an empty database
- **276 backend tests**

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

## Modules

Branches, buildings, floors, rooms, beds - residents, KYC, check-in, bed
assignment, transfer, checkout, QR - invoices, rent generation, payments with a
verify/refund state machine - attendance, gate scan, visitors, gate passes -
food and meal attendance - laundry slots and bookings - complaints, support
queries - staff, roles, permissions - expenses, inventory, assets - reports and
CSV export - notifications, announcements - audit log - organisation and
platform settings - subscriptions, plan limits and usage.

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
| Frontend | `npm run build` -> static files on any CDN or web server |
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
- **KYC upload stores a reference, not a file.** There is no object-storage
  integration; `document_reference` is a string the operator fills in. Building
  it needs a storage decision (S3, GCS, volume) plus signed-URL access control.
- **No frontend unit-test framework.** The build is the static check, plus the
  smoke scripts. Security-critical logic is on the server and covered there; a
  component suite is worth adding as the UI grows.
- **Impersonation is deliberately unimplemented.** `master.impersonate` exists as
  a permission but has no endpoint, and the client refuses to fake it locally —
  that would be a second, unauthenticated route into a tenant.
