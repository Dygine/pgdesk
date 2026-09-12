# Build notes — listing photos, permanent app sessions, map search

Phase 1 of a two-phase piece of work. Phase 2 (the join flow) is described at
the end and is **not** in this build.

---

## 1. Photos on a public listing — 5 KB each, camera or upload

An owner showing free beds can now put up to **six photos** on a branch listing.
Each is stored under **5 KB**, the same rule and the same storage reasoning as a
resident's scanned ID.

Two ways in, deliberately identical to the resident-document flow the owner has
already used:

* **Take photo** — the phone's own camera opens (a plain file input with
  `capture`, which the Android app already supports, so **no new APK is
  needed**). The picture is cropped and shrunk on the device; the full-size
  original never leaves it.
* **Upload image** — accepted exactly as it is if already under 5 KB. Anything
  larger is refused *with its real size*, and the owner can then have it shrunk
  the same way as a camera shot.

### Why a separate compressor from `docScan.js`

`docScan.js` converts to greyscale and stretches contrast. That is right for an
Aadhaar card, where the only thing that matters at 5 KB is whether the number
reads, and colour costs bytes that buy nothing.

A room is the opposite case. A grey photo of a bedroom sells nothing — the
warmth of the light, whether the walls are clean, whether there is a window, all
of it is colour. `photoScan.js` keeps colour and spends the byte budget on it,
which means accepting fewer pixels: a 5 KB colour photo lands around **300–400 px**
on the long side. Good as a card thumbnail on a phone, visibly soft full-screen
on a laptop. That is the trade the 5 KB rule buys, and it is the right one while
storage is PostgreSQL rather than a bucket.

### Enforcement

The 5 KB limit is checked in three places, so no future route can bypass it:

1. the service, on the decoded bytes (so the error states the photo's true size,
   not the size of its base64, which is a third larger and reads as a bug);
2. a `CHECK` on the declared `size_bytes`;
3. a `CHECK` on `octet_length(content)`.

### Payload weight

Search sends **the lead photo only**; the detail sheet fetches the full gallery.
Forty results each carrying six 5 KB photos would be over a megabyte of base64
on a phone that is probably on mobile data. The first photo is the only one a
seeker sees on a search card, so it can be moved to the front — that is a
selling decision and belongs to the owner.

---

## 2. Installed apps stay signed in; browsers expire in 24 hours

### The bug

`AuthService._revoke_all_for()` revoked **every active session for an account**
whenever reuse detection fired. The common trigger was never theft — it was a
deploy:

> the server rotates a refresh token → commits → the instance is replaced
> mid-reply → the app never receives the new token → it retries with the old one
> → the server sees an already-spent token and treats it as a replay.

One unlucky refresh on one device signed out the owner's phone, every manager's
phone and every resident app in the building. That is the reported
"push to git and deploy, then all APKs log out".

### The fix

Every login mints a **token family**; every rotation inherits it. The phone's
chain and the laptop's chain are now different families for the same person, and
reuse detection revokes **only the presenting device's family**.

A stolen token can still be used until the theft is noticed — but that was
already true of the honest half of every ambiguous case, and the account-wide
blast radius was buying nothing except spurious sign-outs. Real remedies stay
account-wide: **signing out, changing a password, or deactivating an account
still revoke every session on every device, immediately.**

### Session length

| Client | Before | Now |
|---|---|---|
| Browser (laptop, desktop) | 14 days | **24 hours**, renewed while in use |
| Installed app (APK) | 10 years | **10 years, renewed on every rotation** |

A laptop is shared, borrowed and left open in a way a phone is not, and its
session lives in a cookie nobody can see or manage. A day means an unattended
machine is safe by the next morning with nobody having to remember to sign out.

The app session is renewed on every rotation, so the clock never runs down on
someone who keeps using it. Uninstalling and reinstalling still asks for a login
— that wipes the Android sandbox, and no app can survive it.

### One more hole closed

`is_native` is now recorded **on the token row** instead of being read from the
`X-PGuru-Client` request header on every refresh. Previously, a proxy that
stripped that header on a single refresh would silently downgrade a permanent
app session to a browser one. Once a chain is native, it stays native.

---

## 3. A real map on Find PG

Leaflet over OpenStreetMap — free, no API key, no billing account attached to a
card that can be forgotten about.

"Near me" only answers the question of someone standing where they want to live.
It answers nothing for the far more common case: finding a PG for a friend, near
a campus, or beside a job that starts next month. For that you have to point at
a place you are not standing in, which needs a map you can see.

Three ways to choose a point, all producing the same `{ latitude, longitude,
label }` so nothing downstream cares which was used:

* **Use my location** — GPS, still one tap
* **Type an area** — geocoded by the API, which proxies Nominatim
* **Tap or drag the pin** — anywhere on earth

Results appear as green dots with a blue radius ring; tapping a dot opens that
PG. A map/list toggle sits in the filter row. PGs whose owner never set a
position cannot be drawn, so the result count says how many are missing rather
than letting the map look emptier than the search really was.

Leaflet is **loaded lazily on first open** — 43.55 KB gzipped in its own chunk,
confirmed by the build. Nobody who never opens the map pays for it.

---

## Verification

* `vite build` — passes. Leaflet correctly split into its own lazy chunk.
* FastAPI app imports cleanly; 242 routes registered, including all four photo
  routes.
* Alembic chain — single head, 15 revisions.
* `test_migrations.py` — **4 passed**, including the two tests asserting that
  migrations and models agree. This is what proves migration `0015` matches the
  `BranchPhoto` model and the new `refresh_tokens` columns exactly.
* Session windows asserted directly: browser 24 h, app 3650 days.
* Suites run and green: `test_search`, `test_resident_documents`,
  `test_tenant_isolation`, `test_permission_catalog`, `test_workflows`,
  `test_check_in`, `test_rbac_matrix`, `test_isolation_matrix`,
  `test_self_checkin`, `test_resident_portal`, `test_platform_settings`,
  `test_auth_login`, `test_config`, `test_errors`, `test_health`,
  `test_security`, `test_database`, `test_pgdesk_updates`, `test_pgguru_updates`.

### A bug found and fixed during this build

The first revision id was `0015_branch_photos_and_token_families` — **37
characters**. Alembic's `alembic_version.version_num` column is `varchar(32)`.
Every migration would have failed on deploy with:

```
psycopg.errors.StringDataRightTruncation: value too long for type character varying(32)
```

Renamed to `0015_photos_and_families` (24 characters). Migration tests pass.

### Pre-existing failures — not introduced here

Confirmed by running the identical tests against an untouched copy of the
previous build. **Six tests fail the same way on both.** All share one root
cause: the test client does not carry the `Secure` refresh cookie over
`http://testserver`, so `/auth/refresh` returns 401.

* `test_auth_session.py` — 4 tests
* `test_qr_login_and_seekers.py::test_a_seeker_signs_up_once_and_enquires_without_new_codes`
* `test_security_hardening.py::test_the_refresh_token_is_absent_from_every_response_body`

Worth fixing, but a separate job — changing them here would have mixed a test-harness
repair into a feature build.

`test_concurrency.py` hangs in a single-CPU container and was not run. It
exercises row locking with real threads and needs a machine with more than one
core to finish.

---

## Deploying this build

1. `cd backend && alembic upgrade head` — creates `branch_photos`, adds
   `family_id` and `is_native` to `refresh_tokens`, and gives every existing
   live token its own family so nobody is left in the migration-window path.
2. Set `BROWSER_SESSION_HOURS=24` in the backend environment.
   `REFRESH_TOKEN_EXPIRE_DAYS` is gone — remove it.
3. `cd frontend && npm install` — pulls in `leaflet@1.9.4`.
4. Deploy the site as usual. **The APK needs no rebuild**: it loads the site from
   `server.url`, so deploying the web app is the app update, and the camera flow
   uses a plain file input that the existing APK already supports.

### What existing users will notice

* Anyone signed in on a **browser** will be asked to sign in again within 24
  hours. That is the intended change.
* Anyone signed in on the **app** stays signed in. Their existing token keeps
  working and is marked native on its next refresh.

---

## Phase 2 — not in this build

The join flow: **I will join this PG** → QR → the owner sees the customer's
details → the owner accepts → the owner adds them as a resident → the portal
never asks for credentials because the person is already in → a notification
lands in the customer's dashboard → the owner's scanned documents appear in the
customer's My Profile.

Held back on purpose. It rewrites resident creation, which performs bed
assignment, rent and invoicing — the most business-critical path in the system.
Bolting it onto a build that also changes photos, sessions and search would make
any regression impossible to attribute, and a zip that looks complete while
breaking check-in for live PGs is worse than one that is honestly partial.
