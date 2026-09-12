/**
 * Remove the downloadable APK from dist/ before Capacitor syncs it.
 *
 * `frontend/public/pgguru.apk` exists so the website can offer it at
 * pgguru.in/pgguru.apk. Vite copies everything in public/ into dist/, and
 * `cap sync` then copies all of dist/ into the app's own assets - so the APK
 * ended up packaged *inside* the APK. 28 MB of an app that exists to open a
 * URL, carrying the previous build of itself around for no reason.
 *
 * This runs between the two steps, so:
 *   npm run build          -> dist keeps the APK   (what Render publishes)
 *   npm run build:android  -> dist loses it, then cap sync  (what ships)
 *
 * Only dist/ is touched. public/pgguru.apk stays where it is.
 */
import { existsSync, rmSync, statSync } from 'node:fs'
import { resolve } from 'node:path'

const target = resolve(process.cwd(), 'dist', 'pgguru.apk')

if (existsSync(target)) {
  const mb = (statSync(target).size / 1024 / 1024).toFixed(1)
  rmSync(target)
  console.log(`  stripped dist/pgguru.apk (${mb} MB) — not bundled into the app`)
} else {
  console.log('  no dist/pgguru.apk to strip')
}
