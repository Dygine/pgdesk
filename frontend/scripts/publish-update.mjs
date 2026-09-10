#!/usr/bin/env node
/**
 * Package a built `dist/` as an update bundle plus a manifest.
 *
 * Run after `vite build`. Produces, inside `dist/updates/`:
 *
 *     pgdesk-<version>.zip   the bundle a phone downloads
 *     version.json           what the app checks on every open
 *
 * Both are written into `dist/` deliberately, so deploying the static site
 * publishes the update in the same step. No second host, no separate upload,
 * and no window where the manifest advertises a bundle that is not there yet.
 *
 * The version comes from package.json. Bump it before building, or the app
 * compares equal versions and correctly decides there is nothing to do.
 *
 *   node scripts/publish-update.mjs --notes "Adds the enquiry inbox"
 */
import { createWriteStream, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const dist = path.join(root, 'dist')
const outDir = path.join(dist, 'updates')

if (!existsSync(dist)) {
  console.error('dist/ not found. Run `npm run build` first.')
  process.exit(1)
}

const pkg = JSON.parse(readFileSync(path.join(root, 'package.json'), 'utf8'))
const version = pkg.version

const args = process.argv.slice(2)
const arg = (name, fallback = null) => {
  const i = args.indexOf(`--${name}`)
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback
}

const notes = arg('notes', `Version ${version}`)
// The lowest native (APK) version that can run this bundle. Raise it only when
// a release genuinely needs new native code - a plugin, a permission. Raising
// it locks every older APK out of the app until the user installs a new one, so
// it is the most expensive number in this file.
const minNative = arg('min-native', pkg.minNativeVersion || null)
const baseUrl = (arg('base-url', process.env.UPDATE_BASE_URL || '') || '').replace(/\/$/, '')

mkdirSync(outDir, { recursive: true })
const zipName = `pgdesk-${version}.zip`
const zipPath = path.join(outDir, zipName)

// Zipped from inside dist/ so the archive root holds index.html, which is what
// the updater expects. Zipping the folder itself would nest everything one
// level deep and the new bundle would load a blank screen.
execFileSync('zip', ['-qr', zipPath, '.', '-x', 'updates/*'], { cwd: dist })

const checksum = createHash('sha256').update(readFileSync(zipPath)).digest('hex')

const manifest = {
  version,
  // Relative when no base URL is given, which works whenever the bundle is
  // served from the same origin as the app - the normal case.
  bundleUrl: baseUrl ? `${baseUrl}/updates/${zipName}` : `/updates/${zipName}`,
  checksum,
  notes,
  releasedAt: new Date().toISOString(),
  ...(minNative ? { minNativeVersion: String(minNative) } : {}),
  ...(baseUrl ? { nativeUrl: `${baseUrl}/pgdesk.apk` } : {}),
}

writeFileSync(path.join(outDir, 'version.json'), `${JSON.stringify(manifest, null, 2)}\n`)

const kb = Math.round(readFileSync(zipPath).length / 1024)
console.log(`published ${version}  (${kb} KB)`)
console.log(`  ${path.relative(root, zipPath)}`)
console.log(`  ${path.relative(root, path.join(outDir, 'version.json'))}`)
if (minNative) console.log(`  minimum APK version: ${minNative}`)
