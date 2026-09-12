# QR sign-in, app-access fixes, PG finder, tab highlight

## Shipping it

1. **Backend**: push. Migration `0012_qr_login_and_seekers` runs on boot. It only
   adds three tables (`login_codes`, `pg_seekers`, `seeker_sessions`) and alters
   nothing existing.
2. **App**: no new APK. No new Capacitor plugin or Android permission was added
   (camera and GPS were already in). Ship as a live update:
   ```powershell
   cd frontend
   npm version patch
   npm run build:update -- --notes "QR sign-in, PG finder"
   ```
3. **Optional env** (backend): `GEOCODER_URL` (default: OpenStreetMap Nominatim)
   and `GEOCODER_USER_AGENT`. Set `GEOCODER_URL=` (empty) to switch area search
   off; the text search keeps working.

## 1. QR sign-in for new residents

Owner creates a resident with app access (or gives it later) and gets a QR on
screen with a 30-minute countdown, plus the email and temporary password as a
fallback. The resident installs the app, taps **Scan QR code to sign in** on the
login screen, is signed in, and lands on **Set your password** (no current
password asked).

The QR holds a one-time key (`PGD1:L:<key>`), never the password. A password
cannot expire after 30 minutes, so a forwarded photo of a password QR would work
forever. The key dies on first use, after 30 minutes, when a newer QR is made,
when the resident sets a password, or when access is turned off.

A new QR without a password reset is only allowed while the resident is still on
the temporary password. After they choose their own, only **Reset password**
works, which they notice. So staff cannot quietly sign in as a resident.

- `POST /auth/qr-login` redeems a key. It is row-locked (two phones cannot both
  win), throttled per IP, and audited.
- `/me/scan` and the guard's `/scan` name a sign-in QR instead of saying "not
  recognised".

## 2. App access after the resident was created (bug fix)

Root cause: `ResidentUpdate` had no `email`, nothing could issue a password
later, and the profile had no Edit button. Ticking "portal login" with no email
silently created nobody.

- Resident profile: **Edit** (all details, including email) and an **App access**
  card with Give access / Show sign-in QR / Reset password / Turn off.
- `POST /residents/{id}/portal-access` (optional `email`), `POST .../reset-password`,
  `POST .../login-code`, `DELETE .../portal-access` (all need `customers.edit`).
- Add-resident form: the email gets the required star when app access is ticked,
  and the tick now sits right under it. The backend refuses a login with no email
  instead of skipping it.
- A login email is refused if a staff account uses it or a live resident login at
  another PG does. Either would make sign-in silently fail.
- Sign-in now prefers the live resident row when an old checked-out row at
  another PG shares the email.

## 3. Change password kept you signed in only for 30 minutes (bug fix)

`/auth/change-password` revoked every session including the current one, so the
phone was signed out when its access token expired. It now revokes all and hands
this device a fresh pair. `current_password` is optional only while
`must_change_password` is set.

## 4. PG finder

- **Owner**: a dashboard card, "Fill your N free beds faster", appears when free
  beds exist in unlisted branches. **Show my free beds** opens one sheet with:
  - which branches to show
  - the enquiry phone number
  - "Use my current location" for branches not yet on the map
  "Not now" hides it for 7 days. Branches → Listing still has the full editor.
- **Seeker** (`/find-pg`, and "Looking for a PG?" on the login screen):
  - Location is detected on open.
  - Areas can be searched by name through the API's geocoder proxy, with a 2 to
    25 km radius.
  - Cards show the room types with a free bed and their "from" rent, plus Call,
    WhatsApp, Directions and Enquire.
- **Seeker accounts**: name, phone and an emailed code, with no password. The
  session is a separate low-power token (`X-PGuru-Seeker`) accepted only by
  `/public/seeker/*`, never tenant data. Enquiries are one tap (15 a day cap),
  and **My enquiries** shows each PG's status.
- **Owner notifications**: every new enquiry now pings the bell of staff with
  `customers.view`.
- **Kept on purpose**: availability is still a band ("a few beds"), now per room
  type, never an exact count, as the security model requires.

## 5. Bottom tab highlight

The active tab gets a filled brand-colour pill, a heavier icon and a bold label,
with a press animation. **More** lights up while the drawer is open or when the
current page is not one of the tabs.

## Tests

317 pass (301 existing + 16 in `tests/test_qr_login_and_seekers.py`). Locally
they need both of these set, or `conftest.py` also rewrites the DB *user* to
`pgguru_test`, and Secure cookies never reach the http test client:

```
TEST_DATABASE_URL=postgresql+psycopg://pgguru:pgguru@localhost:5432/pgguru_test
REFRESH_COOKIE_SECURE=false
```
