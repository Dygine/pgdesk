# PGuru API — backend

Multi-tenant PG / hostel management API. FastAPI · PostgreSQL · SQLAlchemy 2.x · Alembic.

**Status: Phases 3 & 4 — master admin, subscriptions, dynamic RBAC and the property
hierarchy.** Organisations, plans, limits, roles, users, branches, buildings, floors,
rooms and beds are all database-backed and enforced server-side.

**Previously: Milestone 2 — real authentication.** Staff, master admins and residents
authenticate against PostgreSQL with Argon2id hashes and JWT access + refresh tokens.
The React app no longer has a local login path. Resource CRUD arrives in later
milestones. This is not a production-secure system yet; see *What is deliberately not
done* at the bottom.

---

## Prerequisites

| | |
|---|---|
| Python | 3.11+ (developed on 3.12) |
| PostgreSQL | 14+ (developed on 16) |
| Node | 18+ — for the existing frontend, unchanged |

---

## Setup

### 1. Create the database

```bash
sudo -u postgres psql
```
```sql
CREATE USER pgguru WITH PASSWORD 'pgguru' CREATEDB;
CREATE DATABASE pgguru      OWNER pgguru;
CREATE DATABASE pgguru_test OWNER pgguru;   -- the test suite uses its own database
\q
```

### 2. Virtual environment and dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into SECRET_KEY
```

Nothing is hardcoded — database name, user, password and secret all come from `.env`,
which is gitignored.

### 4. Migrate

```bash
alembic upgrade head
```

### 5. Seed (development only)

```bash
python seed.py             # idempotent — safe to re-run
python seed.py --reset     # wipe seeded tenant data first
```

### 6. Run

```bash
uvicorn app.main:app --reload
```

| | |
|---|---|
| API | http://localhost:8000 |
| **Swagger** | **http://localhost:8000/docs** |
| ReDoc | http://localhost:8000/redoc |
| OpenAPI | http://localhost:8000/openapi.json |
| Health | http://localhost:8000/health |
| Database health | http://localhost:8000/health/db |

Frontend, in a second terminal — unchanged:

```bash
cd frontend && npm install && npm run dev      # http://localhost:5173
```

---

## Demo accounts

> **DEVELOPMENT CREDENTIALS ONLY. Fictional. Never use these in production.**

Passwords differ per role on purpose: with one shared password a test can pass while
authenticating as entirely the wrong account.

| Role | Email | Password | Scope |
|---|---|---|---|
| Master Admin | `master@pgguru.local` | `Master@2024` | Platform — no tenant data, 9 master permissions |
| PG Owner | `owner@sunrise.local` | `Owner@2024` | Sunrise Living PG, all 3 branches, 87 permissions |
| Branch Manager | `manager@sunrise.local` | `Manager@2024` | Koramangala + BTM, 55 permissions |
| Resident | `customer@sunrise.local` | `Customer@2024` | Their own stay only, 0 module permissions |
| **PG Owner (2nd tenant)** | `owner@northstar.local` | `Owner@2024` | Northstar Residency — for isolation checks |

The eight accounts the React demo already used still work on `demo1234`:
`rahul@`, `priya@`, `deepak@`, `accounts@`, `reception@`, `security@`, `maintenance@`,
`kitchen@` `sunriselivingpg.com`. `master@pgguru.in` remains as an alias.

Two accounts exist specifically to prove the negative cases:

| Email | What it demonstrates |
|---|---|
| `former@sunrise.local` | Checked-out resident — correct password, still refused (403) |
| `enquiry@sunrise.local` | NULL password hash — cannot authenticate at all (401) |

Passwords are stored as Argon2id hashes. There is no plaintext password anywhere, and
no schema in `app/schemas/` has a `password_hash` field, so one cannot be serialised
by accident.

---

## Authentication

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/login` | — | Staff, master admin and residents |
| POST | `/api/v1/auth/refresh` | — | Rotate the token pair |
| POST | `/api/v1/auth/logout` | bearer | Revoke one session, or all |
| GET | `/api/v1/auth/me` | bearer | The authenticated account |
| POST | `/api/v1/auth/change-password` | bearer | Also clears `must_change_password` |

**Access tokens carry almost nothing** — `sub`, `type`, `principal`, `iat`, `exp`. No
organisation, no role, no permission list. The tenant is resolved from the user record
on every request, so there is no claim a client could tamper with, and a role change
takes effect on the next request rather than the next login.

**Refresh tokens are opaque random strings, stored as SHA-256 digests.** They are
persisted so they can be revoked — a stateless refresh token makes logout a suggestion
rather than an action. SHA-256 rather than Argon2 because these are 384-bit random
values with no dictionary to attack; a slow KDF would only add latency to every refresh.

**Refresh is single-use with reuse detection.** Each call rotates the pair. Presenting
an already-rotated token means either a replay or a stolen token in play alongside the
real one, so every session for that account is revoked.

**Login does not leak which emails exist.** A wrong email and a wrong password return
an identical 401; a test asserts the two responses are byte-identical. Unknown accounts
still pay the cost of a hash verification so the two cannot be told apart by timing.
Account status is only described *after* the password checks out — a suspended user is
told they are suspended, but only once they have proved they own the account.

**Staff and resident tokens are not interchangeable.** The `principal` claim is checked
at the identity layer, so a resident token cannot satisfy a staff dependency even if
some future handler forgets a permission check.

---

## Architecture

```
app/
├── main.py                  wiring only — no business logic
├── core/
│   ├── config.py            env-driven settings + production safety checks
│   ├── database.py          engine, session factory, Base, connectivity probe
│   ├── security.py          Argon2id hashing, JWT access + refresh
│   ├── dependencies.py      identity, tenant scope, require() guards
│   ├── responses.py         the success envelope
│   └── exceptions.py        error classes + handlers
├── models/                  one module per aggregate, not one giant file
├── schemas/                 Pydantic request/response contracts
├── repositories/            tenant-scoped data access
├── services/                business rules (limits, audit)
├── permissions/             catalogue + wildcard engine
├── middleware/              request id and timing
└── api/v1/                  routers, grouped by resource
```

Layering: **router → service → repository → model.** A router never writes a query;
a service never touches a `Request`.

### Two invariants

**1. `organization_id` never comes from the client.** It is resolved from the
authenticated user in `get_current_scope()` and stamped onto writes by
`TenantRepository.add()`. A payload field of that name is ignored.

**2. Cross-tenant reads answer 404, not 403.** `TenantIsolationError` maps to 404
because a 403 would confirm the row exists in someone else's tenant. There is a test
asserting the two responses are byte-identical.

### Permission model

87 tenant permissions across 25 modules, plus 9 master permissions in a separate
namespace. The catalogue is a line-for-line mirror of the React app's
`src/data/permissions.js`, and `tests/test_permission_catalog.py` parses that
JavaScript file and fails if the two ever drift.

Endpoints will be guarded like this:

```python
@router.post("/branches")
def create_branch(
    body: BranchCreate,
    scope: Scope,
    _: None = Depends(require("branches.create")),
): ...
```

Master admins deliberately hold **no role row**. `roles.organization_id` is `NOT NULL`,
so a platform-wide role cannot exist without punching a hole in the isolation that
column enforces; their authority comes from `is_master_admin` plus the fixed master
catalogue. The database rejected the alternative design during development, which is
the constraint doing its job.

### Database-level guarantees

Not left to application code:

- `ck_users_master_has_no_org` — a master admin has no organization; everyone else must have one
- `uq_users_org_email` — email unique **per tenant**; the same person may hold accounts at two PGs
- `uq_users_master_email` — a partial unique index, because `UNIQUE` treats NULLs as distinct
- `uq_branches_org_code` / `uq_branches_org_name` — branch codes unique within a tenant, reusable across tenants
- `uq_roles_org_name`, `uq_permissions_module_action`
- `ck_subscriptions_date_order`, `ck_plans_limits_positive`, `ck_plans_price_non_negative`

Enums are `VARCHAR` + `CHECK` rather than native Postgres enums: adding a value to a
native enum inside a migration locks the table, whereas a CHECK constraint is cheap to
drop and recreate. The database still rejects unknown values.

---

## Migrations

```bash
alembic upgrade head                                  # apply
alembic downgrade -1                                  # one step back
alembic downgrade base                                # drop everything
alembic revision --autogenerate -m "add rooms"        # after editing models
alembic current / alembic history                     # inspect
```

The URL comes from `app.core.config`, not from `alembic.ini`, so credentials live in
exactly one place.

**After changing a model, always check for drift:**
`alembic revision --autogenerate -m "drift"` should produce an empty migration. Delete it.
The current schema passes this check.

---

## Phase 3 & 4 surface

49 routes. Master-only (`require_master`): `/master/dashboard`, `/master/organizations`
(+ `/status`, `/extend`, `/plan`, `/limits`, `/usage`), `/master/plans`,
`/master/usage`, `/master/subscriptions` (+ `/sweep`), `/master/audit`.
Tenant-only (`require_tenant`): `/dashboard`, `/subscription`, `/branches`,
`/buildings`, `/floors`, `/rooms`, `/beds`, `/property/blueprint`, `/roles`,
`/permissions`, `/users`, `/user-branches/{id}`.

**Creating an organisation is one transaction** — organisation, subscription, Owner
role and owner account, or nothing. The temporary password is returned once and stored
only as an Argon2 hash.

**Limits live in the database, never only in React.** `LIMIT_DEFINITIONS` in
`services/subscription_limits.py` drives the counters, the `can_create_*` helpers, the
usage screen and the error messages. Adding a limit is one row plus one plan column.

**Property scoping is denormalised on purpose.** Every level of Building → Floor →
Room → Bed carries `organization_id` and `branch_id`, so the same two filters apply
uniformly instead of a four-table join on every list query.

**Room occupancy is derived from bed status, never stored**, and a database CHECK ties
`status = 'OCCUPIED'` to a non-null `current_customer_id` — an available bed with an
occupant cannot exist.

## Tests

```bash
pytest              # 101 tests
python gatecheck.py # which endpoints each seeded role may call
pytest -v
pytest tests/test_tenant_isolation.py -v      # the critical one
```

Runs against `TEST_DATABASE_URL`, so a test run cannot touch development data. Each
test runs inside a transaction that is rolled back.

Coverage: config safety, password hashing and JWT behaviour, the permission engine,
frontend/backend catalogue parity, error-envelope shape, every database constraint,
health endpoints, the full login matrix (success, wrong password, unknown user,
suspended, deactivated, suspended organisation, checked-out resident, resident with no
password), `/auth/me`, token validation (expired, tampered, wrong key, wrong type),
refresh rotation and reuse detection, logout, password change, and tenant isolation.

`tests/test_tenant_isolation.py` is the one that matters most: two organisations, two
owners, and assertions that Owner A cannot reach Organisation B by any route —
including supplying B's identifiers directly. **It caught a real bug during this
milestone**: `CurrentScope.owns_branch` treated an `all_branches` role as a bypass, so
an owner would have passed the branch guard for *any* branch id in the system,
including another tenant's. Fixed in `app/core/dependencies.py`; the test now covers it.

Subscription-limit and bed-assignment tests arrive with the milestones that build those
endpoints.

---

## Troubleshooting

**`connection refused`** — Postgres isn't running.
`sudo systemctl start postgresql` or `pg_ctlcluster 16 main start`.

**`DATABASE_URL must name the driver`** — use `postgresql+psycopg://`, not
`postgresql://`. This project uses psycopg 3; psycopg2 is not installed.

**`password authentication failed`** — the `pgguru` role doesn't exist or has a
different password. Re-run the `CREATE USER` above.

**`Target database is not up to date`** — run `alembic upgrade head`.

**`Can't locate revision`** — your database is on a revision that is no longer in
`alembic/versions/`. In development: `alembic downgrade base && alembic upgrade head`.

**Autogenerate produces an empty migration** — expected when models and schema agree.
Delete the file.

**Autogenerate wants to drop tables you didn't define** — you are pointed at the wrong
database. Check `DATABASE_URL`.

**CORS errors in the browser** — add the frontend origin to `CORS_ORIGINS` and restart.

---

## What is deliberately not done

Authentication is real. It is not yet hardened. Still missing:

- **No rate limiting or lockout on `/auth/login`.** Nothing stops an attacker trying
  passwords as fast as the network allows. This is the single largest remaining gap and
  should be closed before any deployment.
- **Tokens are in `localStorage`**, which any script on the page can read, so an XSS
  becomes a session theft. Marked as a development simplification in
  `frontend/src/services/api/client.js`; production should move the refresh token to a
  Secure/HttpOnly/SameSite cookie. Everything outside that file goes through
  `tokenStore`, so the change is contained.
- **No password strength policy** beyond a minimum of 8 characters. No breach-list
  check, no complexity rules.
- **Password reset is a data model only.** `password_reset_tokens` exists with the
  right shape — single-use, expiring, hashed, no user id in the token — but no endpoint
  issues or redeems one, and no email is sent.
- **No email verification, MFA, or session listing.**
- **No row-level security.** Isolation is enforced in the repository layer and tested;
  RLS as a second line of defence is worth adding before production.
- **No audit of failed logins.** Successful sign-ins and sign-outs are recorded;
  failures are not, which is backwards for intrusion detection.
- **Impersonation is not implemented.** The `master.impersonate` permission exists but
  no endpoint backs it, and the frontend deliberately refuses rather than falling back
  to a local session switch.
- **`monthly_transactions` usage always reports 0** — billing arrives with the payments
  phase. Every other counter is a live COUNT.
- **Bed assignment is not implemented.** `_set_bed_status` refuses a direct move to
  OCCUPIED, because assigning a resident is a Phase 5 workflow with its own transaction.
- **The owner dashboard's `pending` block returns zeros** (complaints, payments,
  upcoming rent) for the same reason. The keys exist so the screen needs no reshaping.
- **Impersonation has no endpoint.** `master.impersonate` exists as a permission; the
  frontend deliberately refuses rather than switching the local session.
- **Operational data is still the seeded browser store.** Identity is live; rooms,
  beds, residents, invoices and the rest are not. See the bridge note in
  `frontend/src/context/AuthContext.jsx`.
