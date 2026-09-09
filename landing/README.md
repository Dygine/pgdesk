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
