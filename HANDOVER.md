# PGDesk — complete handover

Everything needed to run, build, deploy and debug this project. Written to be
handed to someone (or something) with no prior context.

Owner: **Dygine Software Solution**. Product: **PGDesk**, PG and hostel
management for Indian operators.

---

## 1. What it is

Multi-tenant SaaS. One deployment serves many PG businesses, and no PG can ever
see another's data. Three portals share one React bundle:

| Portal | Route | Who |
|---|---|---|
| Owner / staff | `/app` | 35 screens — rooms, residents, rent, accounts, complaints, gate |
| Resident | `/me` | 10 screens — rent (pay in app), food, laundry, gate QR, moving out |
| Platform admin | `/master` | 9 screens — tenants, subscriptions, platform settings |
| Public | `/signup`, `/find-pg`, `/login`, `/forgot-password` | no account needed |

---

## 2. Where everything lives

```
pgdesk/
├── backend/          FastAPI + PostgreSQL. The brain.
│   ├── app/
│   │   ├── api/v1/endpoints/   14 route modules
│   │   ├── core/               config, security, crypto, dependencies
│   │   ├── models/             SQLAlchemy tables
│   │   ├── services/           all business rules live here
│   │   ├── schemas/            Pydantic request/response
│   │   └── permissions/        the permission catalogue
│   ├── alembic/versions/       12 migrations, 0001 → 0012
│   ├── tests/                  332 test cases
│   ├── seed.py                 demo tenants + accounts
│   └── expire_subscriptions.py daily cron: trial → expired → suspended
│
├── frontend/         React + Vite. Also the Android app.
│   ├── src/
│   │   ├── pages/{auth,org,customer,master,public}/
│   │   ├── components/{ui,domain,layout}/
│   │   ├── services/api/       one module per API area
│   │   ├── lib/                qr, geo, scanner, liveUpdate, nativeSession
│   │   ├── nav/navConfig.js    sidebar is DATA, not markup
│   │   └── routes/index.jsx    all routes
│   ├── android/                Capacitor native project
│   ├── scripts/                build guards + update publisher
│   └── .env.local              VITE_API_URL  (gitignored, must exist)
│
├── landing/          Static marketing page + pgdesk.apk download
└── scripts/          Windows setup helpers
```

**Rule of thumb:** business logic goes in `backend/app/services/`. Endpoints are
thin — read request, call service, commit, shape the envelope.

---

## 3. Deployment

| Thing | Where | Notes |
|---|---|---|
| API | Render service `pgdesk-api` (Singapore) | `https://pgdesk-api.onrender.com` |
| App | Render static site `pgdesk` | `https://pgdesk.dygine.com` |
| Landing | Render static site `pgdesk-get` | `https://get.dygine.com` |
| Database | Neon PostgreSQL | |
| Email | Brevo API | free tier, 300/day |
| Repo | `github.com/Dygine/pgdesk` | push to `main` auto-deploys |

Deploy = `git push`. Render rebuilds both. Migrations run on API boot.

**After a frontend deploy, hard refresh (Ctrl+Shift+R).** A normal refresh
serves cached JavaScript and you will see the old bug and conclude nothing
changed.

---

## 4. Running locally

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then set SECRET_KEY and DATABASE_URL
python -m alembic upgrade head
python seed.py
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

`frontend/.env.local` needs at minimum:

```
VITE_API_URL=http://localhost:8000/api/v1
```

Never set `VITE_SHOW_SEED_ACCOUNTS=true` in anything you ship — it bakes working
demo passwords into the bundle.

### Tests

```powershell
cd backend
python -m pytest          # 332 pass
```

There are **no frontend tests**. Only a build check.

---

## 5. Building the APK

This is the part with the most traps. Follow it exactly.

### Prerequisites

- **JDK** — Java 21 works. Android Studio's bundled JBR works.
- **PowerShell 5.1 does not support `&&`.** Run one line at a time, or install
  PowerShell 7.

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
java -version
```

### Step 1 — API URL (mandatory, baked in permanently)

```powershell
cd frontend
Set-Content -Path .env.local -Value "VITE_API_URL=https://pgdesk-api.onrender.com/api/v1" -Encoding ascii
```

`-Encoding ascii`, not `utf8`. PowerShell 5.1's `utf8` writes a byte-order mark
that some parsers read as part of the variable name.

Must be **https**. The build refuses http, because the refresh cookie is Secure
and the session would die at the first refresh.

### Step 2 — build the web bundle and sync native

```powershell
npm install
npm run build:android
```

**Stop and read the output.** You must see:

```
[info] Found 8 Capacitor plugins for android:
       @capacitor-mlkit/barcode-scanning@8.1.1
       @capacitor/app@8.1.1
       @capacitor/geolocation@8.2.2
       @capacitor/keyboard@8.0.5
       @capacitor/local-notifications@8.3.1
       @capacitor/preferences@8.0.1
       @capacitor/status-bar@8.0.3
       @capgo/capacitor-updater@8.51.15
```

**If it says 4, stop.** Gradle will happily build an APK with no camera, no GPS
and no updater, and nothing will fail. This has cost a full rebuild cycle twice.
Cause is always a stale `node_modules` or an old copy of the source.

Sanity check: the Vite output should include a `jsQR` chunk of ~130 kB and
around **1787 modules transformed**.

### Step 3 — Gradle

```powershell
cd android
.\gradlew.bat assembleDebug
```

`.\gradlew.bat`, not `./gradlew` — the extensionless one is the Unix script.

First build takes ~5 minutes. Want `BUILD SUCCESSFUL`.

### Step 4 — install and publish

```powershell
cd ..
adb install -r android\app\build\outputs\apk\debug\app-debug.apk

cd ..
Copy-Item frontend\android\app\build\outputs\apk\debug\app-debug.apk landing\pgdesk.apk
git add -A
git commit -m "Rebuild APK"
git push
```

### Step 5 — verify on the phone

- **Forgot password?** under the password field
- **PG name** in the sidebar with "Powered by PGDesk" below
- **Permission prompts** after sign-in: notifications → location → camera
- **Gate → Scan with camera** actually opens the camera

### Debug vs release

`assembleDebug` is what these instructions use, because there is **no signing
keystore yet**. A debug APK installs and runs fine.

**A debug APK cannot be upgraded by a signed release APK.** Everyone would have
to uninstall first. Set up signing before handing the APK to real PG owners.

---

## 6. Shipping updates WITHOUT a new APK

Most releases do not need one. The app is a React bundle in a WebView, and the
bundle can be replaced at runtime (`@capgo/capacitor-updater`).

```powershell
cd frontend
npm version patch
npm run build:update -- --notes "What changed"
git add -A; git commit -m "Release"; git push
```

Writes `dist/updates/version.json` and `dist/updates/pgdesk-<version>.zip`
(~257 kB). Installed apps check on open, show an **Update** button, download,
reload. No installer, no permission, no Android dialog.

Rollback is automatic: a bundle that fails to start reverts to the previous one.

### What DOES need a new APK

| Change | New APK? |
|---|---|
| Pages, features, fixes, styling, API changes | **No** |
| New Capacitor plugin | **Yes** |
| New Android permission | **Yes** |
| App icon or name | **Yes** |

Realistically a few times a year. When it happens, raise `minNativeVersion` in
the manifest so older APKs get a "must update" gate instead of being offered a
bundle they cannot run.

Version numbers come from `frontend/package.json`. One `npm version patch` moves
the bundle, the manifest and the Android `versionCode`/`versionName` together.

---

## 7. Email

**Provider: Brevo** (`Master → Platform settings → Email`).

Two transports are supported and switchable:

| | Port | Works where |
|---|---|---|
| **Brevo API** | 443 (https) | everywhere |
| SMTP | 587 / 465 | own VPS, paid hosting |

**Render free tier blocks outbound SMTP ports 25, 465 and 587.** A perfectly
correct Gmail SMTP setup fails there with `[Errno 101] Network is unreachable`,
and nothing about that message points at the host. This is why Brevo exists in
the stack.

Brevo config lives in master settings. The API key is encrypted at rest
(`app/core/crypto.py`, Fernet keyed off `SECRET_KEY`) and has **no read path** —
the settings response says whether a key is stored, never what it is.

**Send test** proves delivery. "Saved" and "delivers" are different claims.

### Known email limitation

The sender is currently `dygine252@gmail.com`, and Brevo rewrites the visible
From to `dygine252@12104625.brevosend.com` because Gmail will not let a third
party send as `@gmail.com`. It works, but residents see a machine-generated
domain on a password reset.

**Fix before real users:** verify `dygine.com` in Brevo (DNS records), then send
as `no-reply@dygine.com`.

Also check whether Brevo's free-plan "Unsubscribe" footer appears on OTP
emails — a resident who clicks it may stop receiving reset codes entirely.

---

## 8. Gotchas that have already cost real time

Read this section before debugging anything.

### Never return a Capacitor plugin from an `async` function

```js
// WRONG — hangs forever, no error, no stack
async function prefs() {
  const { Preferences } = await import('@capacitor/preferences')
  return Preferences
}

// RIGHT
const loadPreferences = () => import('@capacitor/preferences')
const { Preferences } = await loadPreferences()
```

Async functions resolve their return value, and resolution checks for `.then`.
Capacitor plugins are proxies where every property access yields a method stub,
so `.then` looks callable. JS calls it believing it is unwrapping a promise;
Capacitor throws "not implemented" and never invokes resolve or reject. The
promise settles **never**.

Symptom: app frozen on "Restoring your session…" forever. Only visible in
logcat as `"Preferences.then()" is not implemented on android`.

### `notifyAppReady()` must run at startup, not in a component

It lives in `src/main.jsx`. It was once inside `UpdateBanner`, which only
renders after login — so on the login screen it never ran.

### Android sessions do not use the cookie

The WebView serves from `https://localhost` while the API is on another domain,
so every call is cross-site and a `SameSite=Lax` cookie is never attached. On
native, the refresh token is stored in Capacitor Preferences and sent in the
request body. Signalled by the `X-PGDesk-Client: native` header, which also
gives the session a 10-year lifetime instead of 14 days.

### Settings save payload is generated, not hand-written

`buildPayload()` in `MasterSettings.jsx` builds from a `WRITABLE` list mirroring
`platform_settings_service.py`. It used to be a hand-typed object, and fields
added to the form but forgotten there were silently never saved. Cost three
round trips on one dropdown.

**If you add a settings field, add it to `WRITABLE` in both places.**

### A failed refresh is not a sign-out

Only an HTTP **401** from `/auth/refresh` means the saved login is gone. A
network error, a timeout, a 5xx or a host error page means "try again" - the
app keeps the token and shows *Connecting to PGDesk…* with automatic retry
(`SESSION` in `client.js`, `restoreSession` in `AuthContext.jsx`). It used to
delete the token on any failure, which signed everyone out after every deploy.
The server side is `AuthService._is_lost_reply`: a rotated token presented again
within 10 minutes, whose replacement was never used, is a retry, not a theft.
Do not "simplify" either back.

### Render free tier sleeps

~15 minutes idle, then ~50 seconds to wake. The first person to open the app
each morning stares at a splash screen. `/auth/refresh` has a 60-second timeout
so it lands on the login screen rather than hanging forever, but the wait is
real. **Upgrading the `pgdesk-api` service fixes this.**

### PowerShell

- No `&&` in 5.1. Do not substitute `;` — it runs the next command even after a
  failure, which produces stale artefacts that look fresh.
- `.\gradlew.bat`, not `./gradlew`.
- `Set-Content -Encoding ascii` for env files, not `utf8` (BOM).

---

## 9. Security model (do not break these)

- **`organization_id` is never read from a request.** It comes from the
  authenticated principal. This is the whole tenant isolation model.
- **Cross-tenant access returns 404, not 403.** "Forbidden" would confirm the
  record exists.
- **Frontend permission checks are decoration.** Every endpoint re-checks.
- **Secrets are write-only.** SMTP password and Brevo key are encrypted and have
  no read endpoint.
- **Public listing fields are written out by hand** in `PublicService`, never
  serialised from the model, so a new column cannot leak to a public page.
- **Vacancy is published as a band** ("a few beds"), never a count — a number
  would let anyone map a competitor's occupancy.

---

## 10. Feature notes

### Gate / QR

Two directions, both live, both writing to `gate_logs` distinguished by `source`:

- **Guard scans resident** (`POST /scan`, source `qr`)
- **Resident scans gate** (`POST /me/scan`, source `self`) — requires the gate
  QR *and* being inside the branch geofence

Payload format, defined in `backend/app/utils/qr_payload.py` and mirrored in
`frontend/src/lib/qr.js`:

```
PGD1:R:<token>    resident card
PGD1:G:<token>    gate code
```

Geofence default radius 150 m. GPS readings worse than 100 m accuracy are
refused. Every self check-in stores lat/lng/accuracy/distance **including
refusals**, so cheating is auditable afterwards.

Honest limit: this stops friends covering for each other. It does not stop a
mock-location app. Say so to customers.

### Signup and trials

- Owner signup at `/signup` → organisation + owner + **30-day trial**
- Resident signup → verified email + enquiries, **no account** (a seeker belongs
  to no organisation, and every login here is scoped to one)
- `expire_subscriptions.py` daily: TRIAL/ACTIVE → EXPIRED (grace) → SUSPENDED
- **Suspension freezes writes, not reads.** Residents are unaffected — they did
  not miss the payment.

### Public listings

Off by default per branch. `Branches → Listing` turns it on, or the dashboard's
"Show my free beds" card. Seekers have their own low-power accounts - see
`CHANGELOG-QR-FINDER.md`, which also covers QR sign-in for residents.

---

## 11. Known issues / not done

| Issue | Impact |
|---|---|
| **APK is 30 MB** | 69% is a bundled ML Kit barcode engine we never call, plus x86 libs no phone runs. Fix: ABI split (arm64 only), release build with R8, swap to unbundled ML Kit. Target 8–12 MB. |
| **No signing keystore** | Only debug APKs. A release build cannot upgrade over them. |
| **Render free tier** | ~50 s cold start every morning. |
| **Gmail sender** | Brevo rewrites the From domain. Verify `dygine.com`. |
| **No push notifications** | Permission is requested, nothing sends. Needs a Firebase project (`google-services.json` + service account). No way around FCM for closed-app delivery on Android. |
| **KYC files not stored** | Only a text reference. No file storage configured. Real gap for an Indian PG. |
| **No frontend tests** | Build check only. |
| **SMS / WhatsApp** | Structure exists, nothing sends. |
| **Duplicate Render static site** | `pgdesk-get` and `pgdesk` both deployed. Confirm which is the landing page and which is the app. |
| **One gate per branch** | Multiple entrances need a `gates` table. |

---

## 12. Demo accounts (from `seed.py`)

| Role | Email | Password |
|---|---|---|
| Master admin | `master@pgdesk.local` | `Master@2024` |
| PG owner | `owner@sunrise.local` | `Owner@2024` |
| Branch manager | `manager@sunrise.local` | `Manager@2024` |
| Resident | `customer@sunrise.local` | `Customer@2024` |
| Second tenant owner | `owner@northstar.local` | `Owner@2024` |

Eight more staff accounts (`rahul@sunriselivingpg.com` and colleagues) use
`demo1234`.

**These are seed data. Never expose them in a production bundle.**

---

## 13. Debugging on a phone

```powershell
adb devices
adb logcat -c
adb shell am force-stop in.kredo.pgdesk
adb shell monkey -p in.kredo.pgdesk -c android.intent.category.LAUNCHER 1
Start-Sleep -Seconds 20
adb logcat -d > log.txt
Select-String -Path log.txt -Pattern "Capacitor|Console|FATAL|not implemented"
```

Chrome DevTools also works now — `chrome://inspect/#devices` — since
`webContentsDebuggingEnabled` was removed from `capacitor.config.json` (Capacitor
defaults it on for debug builds, off for release, which is correct).

`Capacitor/Console` lines in logcat are the JavaScript console.

---

## 14. Next priorities

1. **Upgrade Render `pgdesk-api`** — kills the cold start. Biggest user-visible win.
2. **Signing keystore + release build + ABI splits** — 30 MB → ~10 MB, and makes
   upgrades possible.
3. **Verify `dygine.com` in Brevo** — real sender domain on password resets.
4. **Push notifications** — needs Firebase from the owner.
5. **KYC file storage** — the oldest outstanding gap.

---

## 15. September 2026 update

Full list in `CHANGELOG-2026-09.md`. What matters operationally:

- **Migration 0013** runs on API boot like the others. Additive only: five new
  tables, new nullable/defaulted columns. Safe on the existing Neon database.
- **No new APK.** Nothing native changed. `npm version patch`, then
  `npm run build:update -- --notes "Staff, notices, payments, P&L, weekly menu"`.
- **Razorpay is per PG, and the money goes to the PG.** Each owner pastes their
  own key id and key secret under Settings → Payments ("Check the keys work"
  calls Razorpay). The secret is write-only, like the Brevo key. For the webhook,
  the owner adds `https://pgdesk-api.onrender.com/api/v1/payments/razorpay/webhook/<their org id>`
  in Razorpay with events `payment.captured` and `payment.failed` - the exact
  URL is shown on the settings screen with a copy button.
- **Only verified payments move a balance** - unchanged. Razorpay payments are
  verified by signature. UPI/bank payments carry a mandatory UTR and wait in
  Payments for someone with `payments.verify`.
- **Honest limit on UPI inside Razorpay Checkout in the app:** cards, net
  banking and UPI ID/QR work in the WebView. Razorpay's "pay with installed UPI
  app" intent may not open apps from inside the WebView. The separate UPI option
  (drawn QR plus `upi://` link) does not depend on this. If owners need the
  in-checkout app intent, that is a small native change (URL interception in
  `MainActivity`) and therefore a new APK.
- **Menus:** the weekly menu is the menu. One-day specials older than 7 days are
  deleted on every menu save and by `expire_subscriptions.py`. Meal attendance
  history is untouched - it never pointed at menu rows.
- **Staff vs Users:** Staff = the workforce (no login needed), Users = logins.
  Salaries paid from Staff are ordinary `Salary` expenses tagged with the staff
  member and month.
