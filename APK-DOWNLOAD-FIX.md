# Why the download gives the OLD app — and how to fix it

Short version:

1. The `pgdesk.apk` currently served at **get.dygine.com** is the **old
   self-contained build**. It does **not** load pgdesk.dygine.com, so it shows old
   screens and can never update itself. That is why every device gets the old app,
   no matter how many times you re-download.
2. The **"29.54 MB → 30 MB" jump is not a bug.** Same file, two units.
3. Fix = **rebuild the APK from the current code and replace the file**, then push.
   Plus a small cache-busting change already made to the landing page so the next
   new APK actually reaches phones.

---

## 1. The APK on the download page is the old build (this is the real problem)

An `.apk` is just a ZIP. Inside it, `assets/capacitor.config.json` decides how the
app behaves. The file currently in `landing/pgdesk.apk` contains:

```json
"server": { "androidScheme": "https" },          // ← no "url"
...
"CapacitorUpdater": { "autoUpdate": false, ... }  // ← old self-updater still baked in
```

- **No `server.url`** → the app runs its own bundled copy of the screens, not the
  website. So it shows whatever was built into it, forever.
- **`CapacitorUpdater` present** → this is the old self-updater that looked for new
  versions at a path *inside the app itself*, which is exactly why no installed
  copy ever updated.

The **current source** (`frontend/capacitor.config.json`) is already the new
thin-wrapper build:

```json
"server": { "url": "https://pgdesk.dygine.com", "errorPath": "offline.html", "cleartext": false }
// and no CapacitorUpdater block
```

So the **code** was migrated to the thin wrapper, but the **APK on the download
page was never rebuilt from it.** Your mental model ("open the app → it loads
pgdesk.dygine.com → deploys update it automatically") is correct — but only for a
device running a *new* APK. The one on get.dygine.com is still the old one.

### Verify which build any `.apk` is (don't take my word for it)

```powershell
Expand-Archive .\landing\pgdesk.apk -DestinationPath $env:TEMP\apkcheck -Force
Get-Content $env:TEMP\apkcheck\assets\capacitor.config.json
Remove-Item $env:TEMP\apkcheck -Recurse -Force
```

- **New build** → shows `"url": "https://pgdesk.dygine.com"`, **no** `CapacitorUpdater`.
- **Old build** → no `url`, `CapacitorUpdater` present. ← what's there now.

---

## 2. The "29.54 MB then suddenly 30 MB" is normal

The file is **30,762,142 bytes**. That is:

- **29.34 MiB** when you divide by 1024 → what the **download progress bar** counts.
- **30.76 MB** when you divide by 1000 → what the **"downloaded" notification** shows.

Android/Chrome count progress in MiB (÷1024) and report the finished size in MB
(÷1000), so it always looks like a small jump right at the end. Nothing is
corrupted and the download is complete. Ignore it.

---

## 3. The fix, step by step

You have to do steps 1–5 on your machine — I can't build an Android APK here.

**1. Rebuild the APK from current code (the thin wrapper):**

```bash
cd frontend
npm install
npm run build:android          # checks env, vite build, cap sync android
cd android
./gradlew assembleRelease      # or assembleDebug for a quick test build
```

**2. Copy it into the landing folder and rename:**

```powershell
# release build:
Copy-Item app\build\outputs\apk\release\app-release.apk ..\..\landing\pgdesk.apk
# (debug build path is app\build\outputs\apk\debug\app-debug.apk)
```

**3. Verify it is the NEW build** using the snippet in section 1 — you must see
`pgdesk.dygine.com` and **no** `CapacitorUpdater`. Also confirm no demo
credentials leaked (the `Owner@2024` check already in `landing/README.md`).

**4. Bump the cache-buster.** In `landing/index.html`, near the bottom, change:

```js
var APK_VERSION = '2026-09-11';   // ← set to today's date
```

This makes the browser treat the new file as a new URL instead of serving the old
cached one.

**5. Set the CDN cache header once** (so Render's CDN also stops serving the stale
file). Render → the `pgdesk-get` static site → **Settings → Headers → Add header**:

| Field | Value |
|---|---|
| Path | `/pgdesk.apk` |
| Name | `Cache-Control` |
| Value | `no-cache, must-revalidate` |

**6. Commit + push.** get.dygine.com redeploys with the new APK.

---

## 4. After this is done

- **Website / in-app changes:** `git push` only. Installed apps refresh themselves,
  because they load the website. No new APK.
- **New APK needed only for native changes:** a new plugin or permission, the app
  icon or name, or a new website address.

---

## 5. "It worked yesterday, not today"

I can't tell from here what changed on which day — but the one checkable fact is
that **the file in the repo right now is the old build**, so any device downloading
it today gets the old app. Whenever you're unsure which build a given `.apk` is,
run the verify snippet in section 1 and you'll know for certain.
