# PGuru landing + APK download

> **⚠ The `pgguru.apk` in this folder is the OLD self-contained build.**
> It has no `server.url`, so it does **not** open pgguru.in — it runs its
> own stale bundled screens and can never update itself. Anyone who downloads it
> gets the old app, on every device. **Rebuild it (see below) and replace this
> file before relying on the download.** Full story + how to verify any `.apk`:
> `../APK-DOWNLOAD-FIX.md`.

Deployed as its own Render **Static Site** from this same repository.

| Render setting | Value |
|---|---|
| Root Directory | `landing` |
| Build Command | *(leave empty)* |
| Publish Directory | `.` |

## The APK

`pgguru.apk` must sit in this folder, next to `index.html`.

Copy it from your build output and rename it:

```powershell
Copy-Item frontend\android\app\build\outputs\apk\debug\app-debug.apk landing\pgguru.apk
```

**Verify it is the clean build before committing.** A build made with
`VITE_SHOW_SEED_ACCOUNTS=true` ships working demo credentials inside the APK:

```powershell
Expand-Archive landing\pgguru.apk -DestinationPath $env:TEMP\apkcheck -Force
Select-String -Path $env:TEMP\apkcheck\assets\public\assets\*.js -Pattern "Owner@2024" -SimpleMatch
```

No output means clean. Any output means rebuild with `npm run build:android`
before you push.

## Two values to keep in step

Both are hardcoded in `index.html`:

- the web app URL, `https://pgguru.in`, in two places
- the version string `v1.0` under the download button

## Note on repository size

The APK is around 4 MB. Git stores every version you commit forever, so if you
push a new APK on each build the repository grows by 4 MB each time. For a
handful of releases this is fine. Past that, attach the APK to a GitHub Release
instead and point the download button at the release URL.


## Rebuilding the APK

The APK here is a **build artefact**, not source. It goes stale the moment the
app changes, and a stale APK is worse than none: it looks current and silently
lacks whatever shipped since.

```bash
cd frontend
npm install
npm run build:android          # vite build + cap sync android
cd android && ./gradlew assembleRelease
cp app/build/outputs/apk/release/app-release.apk ../../landing/pgguru.apk
```

## Updates

The app opens https://pgguru.in inside itself, so deploying the
website updates the app too - `git push` and you are done. A new APK is only
needed for native changes (a plugin, a permission, the icon or name) or a new
website address. See HANDOVER.md §6.

## Verify which build an APK is

An `.apk` is a ZIP. What matters is `assets/capacitor.config.json` inside it:

```powershell
Expand-Archive .\landing\pgguru.apk -DestinationPath $env:TEMP\apkcheck -Force
Get-Content $env:TEMP\apkcheck\assets\capacitor.config.json
Remove-Item $env:TEMP\apkcheck -Recurse -Force
```

- **New (correct) build** - shows `"url": "https://pgguru.in"` and has **no**
  `CapacitorUpdater` block.
- **Old build** - no `url`, and a `"CapacitorUpdater"` block is present.

Do **not** judge new-vs-old by file size. With `server.url` set, Capacitor still
bundles the web files as an offline fallback, so a correct build can be a similar
size to the old one. Judge by the config, not the megabytes.

## Making a new APK actually reach phones (cache)

`pgguru.apk` is served from the same URL every release, so browsers and the CDN
keep handing out the previously cached copy - this is why a "new" download can
still install the old app. Two things fix it:

1. **Browser cache - already wired.** `index.html` appends `?v=APK_VERSION` to the
   download link, so a new upload looks like a new URL. **Bump `APK_VERSION`**
   (near the bottom of `index.html`) to that day's date every time you replace
   the APK.
2. **CDN cache - set once.** On Render, open the `pgguru-get` static site →
   **Settings → Headers → Add header**:
   - Path: `/pgguru.apk`
   - Name: `Cache-Control`
   - Value: `no-cache, must-revalidate`

   `no-cache` still lets the file be stored, but forces the CDN to revalidate, so
   a changed APK is re-fetched and an unchanged one returns a fast 304.
