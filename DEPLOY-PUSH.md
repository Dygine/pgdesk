# Push notifications — deployment and test guide

Everything is built. This is the order to apply it and how to prove it works.

---

## 1. What changed

**New files (8)**

| Path | What it is |
|---|---|
| `backend/app/models/device_token.py` | `device_tokens` table — one row per phone |
| `backend/app/schemas/push.py` | Request shapes for register / revoke / key |
| `backend/app/services/push_service.py` | FCM sender and the queue sweep |
| `backend/app/services/push_dispatcher.py` | Background loop + rent reminders |
| `backend/alembic/versions/0017_push_notifications.py` | The migration |
| `frontend/src/lib/push.js` | Token registration and tap routing |
| `frontend/src/pages/master/PushCard.jsx` | Master Admin notification module |
| `frontend/android/app/google-services.json` | Your Firebase config |
| `frontend/android/app/src/main/res/drawable/ic_stat_notify.xml` | Status-bar icon |
| `frontend/android/app/src/main/res/values/colors.xml` | Notification accent |

**Changed files (22)** — listed in full by `git status` after you apply.

**Deleted** — the whole `in/kredo/` package tree under
`frontend/android/app/src/{main,test,androidTest}/java/`. These must be gone, not
just emptied: a leftover directory produces a build error that reads as though
the rename failed.

---

## 2. Package name change

`in.kredo.pgguru` → **`in.pgguru.app`**, in 7 files plus 3 folder renames.

This was done now because it can never be done after a Play Store release.
Your Firebase app is registered against the new name, and the JSON was
machine-checked against `build.gradle` before packaging.

**Consequence:** anyone holding the old APK must uninstall and reinstall.
Android treats a different package name as a different app, so there is no
update path. Nobody is on the Play Store yet, so this only affects test devices.

Your signing keystore is untouched.

---

## 3. Deploy order

Run these in order. Steps 1–3 are safe on live data and change no behaviour
until you switch push on in step 5.

### Step 1 — backend dependencies
```
cd backend
pip install -r requirements.txt
```
Two additions: `google-auth` (FCM v1 authenticates with a signed service
account, not the retired server key) and `httpx` promoted from test-only to a
runtime dependency.

### Step 2 — migration
```
alembic upgrade head
```
Creates `device_tokens`, adds three columns to `notifications`, adds seven to
`platform_settings`. Non-destructive, and `downgrade` is exact.

Note: existing notification rows are stamped `pushed_at = now()` by the
migration. Without that, the first sweep would push every historical
notification in your database to every phone at once.

### Step 3 — deploy backend + frontend
Normal `git push`. The dispatcher starts with the app and does nothing until
push is enabled.

### Step 4 — paste the Firebase key
Master → Settings → **Push notifications**.

Paste the **service account key** (Firebase → Project settings → Service
accounts → Generate new private key). Not `google-services.json` — the screen
rejects that file by name if you mix them up.

Leave "Firebase project ID" blank; it is read from the key.

### Step 5 — turn it on
Same card: switch **Send push notifications** on, then Save.

### Step 6 — build and install the APK
```
cd frontend
npm install
npm run build:android
cd android && ./gradlew assembleRelease
```
Uninstall any old PGuru first — different package name, no upgrade path.

### Step 7 — prove it
Open the app, sign in, allow notifications. Then Master → Settings →
**Send test notification**. The card timestamps itself when Firebase accepts.

---

## 4. Server test checklist

| # | Test | Expected |
|---|---|---|
| 1 | `alembic upgrade head` | No error; `device_tokens` exists |
| 2 | `alembic downgrade -1` then `upgrade head` | Both clean |
| 3 | Sign in on phone, allow notifications | Row appears in `device_tokens` with your user id |
| 4 | Master → Send test notification | Arrives on phone; `fcm_verified_at` set |
| 5 | **Close the app completely** (swipe away), post an announcement | Notification arrives within ~10s |
| 6 | Tap the notification | App opens on the announcements screen |
| 7 | Raise an invoice for a resident | That resident's phone gets "New invoice" |
| 8 | Record a payment | Resident gets "Payment recorded" |
| 9 | Resident raises a complaint | Owner/staff phone gets it |
| 10 | Sign out on the phone | `revoked_at` set on that token row |
| 11 | Sign in as a *different* person on the same phone | Token moves to the new owner; old owner gets nothing |
| 12 | Turn "To residents" off, post an announcement | Staff get it, residents do not; row marked `audience disabled` |
| 13 | Turn push off entirely, post an announcement | Nothing pushed; bell inside the app still shows it |
| 14 | Set an invoice due date 3 days out, wait for the hourly job | One reminder, and only one — never a repeat |
| 15 | Paste a deliberately wrong key, send test | Readable error, `fcm_verified_at` cleared |

Tests 5, 11 and 14 are the ones that matter most. Test 5 is the whole feature.
Test 11 is the bug that would otherwise send one resident's rent reminders to
another. Test 14 catches a reminder loop that would message people hourly.

---

## 5. Things that will bite you

**Redmi, Realme, Vivo, Oppo.** These block background Firebase by default —
20–40% of push failures across the industry are OEM battery managers, and those
handsets are most of your resident base. The permission onboarding now includes
a step that opens the battery settings. If a test phone gets nothing while a
Pixel works, this is why: Settings → Apps → PGuru → Battery → No restrictions,
and enable Autostart.

**Free-tier hosting sleeps.** If your Render instance is asleep, the sweep is
not running. Nothing is lost — the queue is a database table and drains on
wake — but delivery is delayed until the first request wakes it.

**Delivery is up to 10 seconds late.** The sweep runs on a timer. Correct for
invoices, announcements and reminders. It would not be correct for chat, which
this is not.

**A notification with no registered phone is still marked sent.** That is not a
failure — the person simply has not installed the app. The in-app bell still
shows it.

---

## 6. What was deliberately not done

**Per-event toggles.** You get residents / staff / off. Nine separate switches
for nine notification kinds is a settings screen nobody reads and four support
questions a month.

**A worker service.** The sweep runs inside the web process. At your size a
second Render instance plus a queue broker is infrastructure bought for a
problem you do not have. When one PG passes ~500 residents,
`PushService.dispatch_pending` moves to a real worker unchanged — that is why
delivery state lives on the notification row rather than inside the loop.

**iOS.** The plugin supports it, but it needs a paid Apple Developer account
and an APNs key. Nothing here blocks adding it later.

---

## 7. How push reaches every feature

Push was attached to the `notifications` table, not to eight call sites. Every
service that already writes a notification row now gets push for free:

`billing_service` (invoices, payments, verification) · `support_service`
(announcements, complaints, queries) · `operations_service` (visitors, gate
passes) · `notice_service` (checkout) · `resident_service` ·
`payment_gateway_service` · `subscription_lifecycle`

None of those files was modified. Any notification kind you add next year is
pushed automatically, and there is exactly one place to look when something is
not delivered.
