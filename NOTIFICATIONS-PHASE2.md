# Notifications — crash fix, per-user toggle, master broadcast

Three changes since the last package.

---

## 1. The crash fix (most important)

`frontend/android/app/proguard-rules.pro`

The release build has `minifyEnabled true`, and that file was empty — nothing
but commented-out boilerplate. Capacitor finds its plugins at runtime by reading
the `@CapacitorPlugin` annotation off the class, and R8 strips runtime
annotation metadata unless told not to.

The result was a native crash the moment `PushNotifications.checkPermissions()`
ran:

```
FATAL EXCEPTION: CapacitorPlugins
java.lang.NullPointerException
  at com.getcapacitor.Plugin.getPermissionStates
  at PushNotificationsPlugin.checkPermissions
```

A native crash on the plugin thread cannot be caught from JavaScript. The
process is simply gone.

This was a latent defect in the project before push existed. Every other plugin
uses `requestPermissions()`, which null-checks the annotation; `checkPermissions()`
does not. Push was the first thing to take that path.

The file now also keeps `SourceFile,LineNumberTable`, so the next crash report
names a file and a line instead of `r8-map-id-7fec3de08ec1...`.

**Rebuild with `gradlew clean` first** — R8 caches aggressively.

---

## 2. Per-person notification switch

Every account — owner, warden, resident, master admin — gets one switch in
their profile menu, top right.

**Backend**
- `backend/app/models/user.py` — `notifications_enabled`
- `backend/app/models/customer.py` — `notifications_enabled`
- `backend/alembic/versions/0018_notification_preference.py`
- `backend/app/api/v1/endpoints/support.py` — `GET`/`PATCH /notifications/preferences`
- `backend/app/services/push_service.py` — the sweep honours it

**Frontend**
- `frontend/src/components/layout/AppShell.jsx` — the switch
- `frontend/src/services/api/notificationApi.js`

**Two decisions worth knowing.**

Turning it off stops push to that person's phones. It does **not** hide the
notification — the bell inside the app still shows everything. "Do not buzz my
phone" and "hide my invoices from me" are different requests, and only one of
them was made.

It defaults to **on**. Default-off sounds more polite and is worse: an invoice
notification that never arrives because nobody found a setting is
indistinguishable from a broken feature, and the person who wanted it never
learns it exists.

The preference lives on the person, not the device. Someone who turns it off and
later installs the app on a new phone has not changed their mind.

---

## 3. Master broadcast

Master → Settings → **Broadcast to all users**.

- `backend/app/api/v1/endpoints/master.py` — `POST /master/broadcast`, `GET /master/broadcast/reach`
- `backend/app/schemas/push.py` — `BroadcastRequest`
- `frontend/src/pages/master/BroadcastCard.jsx`
- `frontend/src/pages/master/MasterSettings.jsx`
- `frontend/src/services/api/platformSettingsApi.js`

Audience: everyone, owners and staff only, or residents only.

**How it delivers.** It writes ordinary `Notification` rows and stops. The same
sweep that handles invoices and announcements picks them up — so the per-person
opt-out, the audience toggles, retries and delivery tracking all apply for free
rather than being reimplemented.

Each row carries the **recipient's** `organization_id`, not the operator's (who
has none). Tenant isolation is intact: a resident sees it through exactly the
same query as every other notification.

**Why it is not an Announcement.** An Announcement belongs to one PG and is
written by its owner. This crosses tenants, which only the operator may do, and
must not be attributed to a PG — "your PG says the app is down on Sunday" is a
lie that sends calls to the wrong people.

**The guard rails.** The reach is shown before you type. The confirmation
checkbox names the number. The button says it again. The API refuses without
`confirm: true`. A broadcast cannot be recalled once the sweep has run, and
"sent to 4,000 people by accident" is not a recoverable mistake.

---

## Deploy order

```powershell
# 1. migration — on NEON, not localhost
cd backend
python -m alembic -x db_url="<your neon url>" upgrade head
#   expect exactly: 0017_push_notifications -> 0018_notification_preference

# 2. push (backend + both screens ship this way)
cd ..
git add -A
git commit -m "Notification preference per user, master broadcast, R8 keep rules"
git push origin main

# 3. APK — needed ONLY for the crash fix
cd frontend\android
.\gradlew clean
cd ..
npm run build:android
cd android
.\gradlew assembleRelease
```

The toggle and the broadcast are web + backend, so they arrive by `git push`.
The APK rebuild is purely for the ProGuard fix.

---

## Test checklist

| # | Test | Expected |
|---|---|---|
| 1 | Open app, sign in, press Allow | No crash — this is the one that matters |
| 2 | Profile menu, top right | "Notifications" switch, on by default |
| 3 | Turn it off, post an announcement | No push; the bell inside the app still shows it |
| 4 | Turn it back on, post again | Push arrives |
| 5 | Sign in as a resident, check profile menu | Same switch, same behaviour |
| 6 | Master → Settings → Broadcast | Reach counts show before typing |
| 7 | Send button before ticking confirm | Disabled |
| 8 | Send to "Residents only" | Only residents get it; count matches |
| 9 | Broadcast with one user opted out | They are skipped on the phone, still see it in-app |
| 10 | `notifications` table after a broadcast | One row per recipient, `pushed_at` filling in |

Test 1 first. Everything else is unreachable until the app stays open.

---

## Still outstanding

The Neon database password was pasted into a chat during setup and is still the
live one. Rotate it: Neon → Roles → `neondb_owner` → Reset password, then update
`DATABASE_URL` in the Render `pgdesk-api` environment.
