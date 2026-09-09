# PGDesk on Android

The Android app is **the same React application** as the web build, running in a
Capacitor WebView. There is no second frontend, no second backend, no second
database and no duplicated business logic.

```
React / Vite  ──▶  dist/  ──▶  Capacitor  ──▶  Android WebView
                     │                              │
                     └──────────── HTTPS ───────────┴──▶  FastAPI  ──▶  PostgreSQL
```

| | |
|---|---|
| Application ID | `in.kredo.pgdesk` |
| App name | PGDesk |
| minSdk / targetSdk | 24 (Android 7.0) / 36 |
| Permissions | `INTERNET` only |
| Project path | `frontend/android` |

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Node.js | 20 or 22 | Same one the web build uses |
| JDK | **21** | Must be a full JDK, not a JRE — a JRE has no `javac` and Gradle fails with "does not provide the required capabilities: [JAVA_COMPILER]" |
| Android Studio | Ladybug or newer | Bundles its own JDK, which is usually the easiest route |
| Android SDK | Platform 36, Build-Tools 36.0.0, Platform-Tools | Install via Android Studio → SDK Manager |

Environment variables:

```powershell
# Windows (PowerShell) — adjust paths to your install
setx ANDROID_HOME "$env:LOCALAPPDATA\Android\Sdk"
setx JAVA_HOME "C:\Program Files\Android\Android Studio\jbr"
```

```bash
# macOS / Linux
export ANDROID_HOME="$HOME/Android/Sdk"
export JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
export PATH="$ANDROID_HOME/platform-tools:$PATH"
```

Android Studio writes `frontend/android/local.properties` with `sdk.dir` on
first open. That file is machine-specific and is not committed.

---

## The one thing you must get right: the API URL

`VITE_API_URL` is baked into the bundle **at build time**. There is no way to
change it once the APK is built.

On a device, `localhost` is the phone — not your laptop. A bundle built without
`VITE_API_URL` produces an app that installs, launches, shows a login form and
can never reach anything.

`src/services/api/client.js` refuses to start on a device when the configured
URL is missing, points at `localhost` / `127.0.0.1` / `10.0.2.2`, or is not
HTTPS. You get a clear error instead of a mystery.

```bash
VITE_API_URL=https://api.yourdomain.com/api/v1 npm run build
npx cap sync android
```

For testing against a laptop from a real handset, put the API behind a real
HTTPS tunnel (Cloudflare Tunnel, ngrok) and use that hostname. `10.0.2.2` — the
emulator's alias for the host — is deliberately rejected because it is plain
http, and the session cookie will not survive (see below).

---

## Session and cookies on Android

This is the part that bites, so it is worth understanding rather than
copy-pasting.

PGDesk keeps the refresh token in an **HttpOnly, Secure cookie** scoped to
`/api/v1/auth`. That is the correct design: script on the page cannot read the
long-lived credential.

In Capacitor the WebView is served from `https://localhost`, while your API is
on another host. Every API call is therefore **cross-site**, and the refresh
cookie is a **third-party cookie**. Two consequences:

**1. The cookie must be allowed to travel cross-site.** Set these on the API:

```
CORS_ORIGINS=https://app.yourdomain.com,https://localhost
REFRESH_COOKIE_SAMESITE=none
REFRESH_COOKIE_SECURE=true
```

A `SameSite=lax` cookie is simply not attached to a cross-site request, and
`SameSite=none` is invalid without `Secure`. Both are already enforced by
`app/core/config.py:assert_production_safe()`.

**2. The WebView must accept third-party cookies.** Android's WebView refuses
them by default, and Capacitor's `Bridge` does not change that — only the
Cordova compatibility layer calls `setAcceptThirdPartyCookies`, and a plain
Capacitor app never goes through it.

`MainActivity.java` therefore calls it explicitly. Without those lines the
failure is nasty and slow to diagnose: login succeeds (the access token comes
back in the response body), then the session dies about 30 minutes later and on
every cold start, because `POST /auth/refresh` arrives with no cookie.

**Why not put the refresh token in the response body?** `EXPOSE_REFRESH_TOKEN_IN_BODY`
exists for non-browser clients, but `assert_production_safe()` refuses it in
production on purpose — a token in the body is readable by anything that can
hook `fetch`. A WebView still runs your JavaScript, so that risk is real here
too. Keeping the cookie HttpOnly and allowing it natively is the safer trade.

The `X-PGDesk-Auth` CSRF header works unchanged: `https://localhost` is a normal
origin subject to preflight, which is exactly the property the header relies on.

---

## Commands

```bash
cd frontend

# install (once)
npm install

# build the web bundle with the real API origin, validate it and sync.
# build:android runs scripts/check-android-env.mjs first, which refuses a
# missing / http / localhost / placeholder URL and refuses seed accounts.
VITE_API_URL=https://api.yourdomain.com/api/v1 npm run build:android

# open in Android Studio
npx cap open android
```

Run it:

```bash
# emulator or attached device, from Android Studio's Run button, or:
npx cap run android
```

Build artifacts from the command line:

```bash
cd android

./gradlew assembleDebug      # app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease    # app/build/outputs/apk/release/
./gradlew bundleRelease      # app/build/outputs/bundle/release/app-release.aab  (Play Store)
```

On Windows use `gradlew.bat`.

**Always `npm run build:android` before building the APK.**
Gradle packages whatever is in `android/app/src/main/assets/public`; it does not
know your React source changed.

---

## Release signing

No keystore and no password is in this repository, and `.gitignore` blocks
`*.jks`, `*.keystore` and `keystore.properties`.

Create a keystore once, and keep it somewhere backed up — losing it means you
can never update the app on Play:

```bash
keytool -genkey -v -keystore pgdesk-release.jks \
        -keyalg RSA -keysize 2048 -validity 10000 -alias pgdesk
```

Then either create `frontend/android/keystore.properties` (gitignored):

```properties
storeFile=C:/keys/pgdesk-release.jks
storePassword=...
keyAlias=pgdesk
keyPassword=...
```

or, for CI, set environment variables instead — the Gradle config checks the
file first and falls back to them:

```
PGDESK_KEYSTORE, PGDESK_KEYSTORE_PASSWORD, PGDESK_KEY_ALIAS, PGDESK_KEY_PASSWORD
```

If neither is present the release build still runs and produces an **unsigned**
artifact, with a warning in the Gradle log. That is intentional so a fresh
clone builds without secrets.

---

## Android behaviour that is wired up

`src/native/android.js`, a no-op on the web:

| Concern | Behaviour |
|---|---|
| Hardware back button | Closes an open dialog first; exits from a portal root (`/app`, `/master`, `/me`, `/login`); otherwise navigates back |
| Status bar | Light icons on the brand slate background, not overlaying the WebView |
| Keyboard | Sets `--kb-height` and `.kb-open`, so the fixed bottom nav hides instead of covering the focused field |
| Safe areas | `viewport-fit=cover` plus the existing `.safe-b` (`env(safe-area-inset-bottom)`) |
| App resume | Emits `pgdesk:resume` so screens can revalidate a stale 30-minute token |
| Network errors | Already handled — `client.js` raises `NetworkError` with a human message |

Nothing else is native. No camera, storage, location or push — the app requests
`INTERNET` and nothing more.

---

## Troubleshooting

**"does not provide the required capabilities: [JAVA_COMPILER]"** — `JAVA_HOME`
points at a JRE. Point it at a JDK (Android Studio's bundled `jbr` works).

**App opens to a blank screen** — the web bundle was not synced. Run
`npm run build:android`.

**Login works, then you are signed out later** — the third-party cookie path.
Check `REFRESH_COOKIE_SAMESITE=none`, `REFRESH_COOKIE_SECURE=true`,
`https://localhost` in `CORS_ORIGINS`, and that `MainActivity.java` still has
the `setAcceptThirdPartyCookies` call.

**CORS errors in `chrome://inspect`** — add `https://localhost` to
`CORS_ORIGINS` and confirm `allow_headers` includes `X-PGDesk-Auth`.

**Cannot reach the API at all** — you built without `VITE_API_URL`, or with an
http one. The app should have told you at startup; check logcat.
