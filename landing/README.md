# PGDesk landing + APK download

Deployed as its own Render **Static Site** from this same repository.

| Render setting | Value |
|---|---|
| Root Directory | `landing` |
| Build Command | *(leave empty)* |
| Publish Directory | `.` |

## The APK

`pgdesk.apk` must sit in this folder, next to `index.html`.

Copy it from your build output and rename it:

```powershell
Copy-Item frontend\android\app\build\outputs\apk\debug\app-debug.apk landing\pgdesk.apk
```

**Verify it is the clean build before committing.** A build made with
`VITE_SHOW_SEED_ACCOUNTS=true` ships working demo credentials inside the APK:

```powershell
Expand-Archive landing\pgdesk.apk -DestinationPath $env:TEMP\apkcheck -Force
Select-String -Path $env:TEMP\apkcheck\assets\public\assets\*.js -Pattern "Owner@2024" -SimpleMatch
```

No output means clean. Any output means rebuild with `npm run build:android`
before you push.

## Two values to keep in step

Both are hardcoded in `index.html`:

- the web app URL, `https://pgdesk.dygine.com`, in two places
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
cp app/build/outputs/apk/release/app-release.apk ../../landing/pgdesk.apk
```

## Live updates

Most releases do **not** need a new APK. Anything that is only React, CSS or API
changes ships as a bundle the installed app downloads itself:

```bash
cd frontend
npm version patch              # bumps package.json, the bundle and the APK together
npm run build:update -- --notes "What changed"
```

That writes `dist/updates/version.json` and `dist/updates/pgdesk-<version>.zip`.
Deploy the static site as usual and installed apps pick it up on next open.

A new APK is only required when native code changes: a new Capacitor plugin, a
new Android permission, or a different app icon or name. In that case bump
`minNativeVersion` in the manifest so older APKs are told to reinstall rather
than being offered a bundle they cannot run.
