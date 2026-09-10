/**
 * Updating the app without reinstalling it.
 *
 * PGDesk is a React bundle inside a WebView, so nearly everything that changes
 * between releases - pages, fixes, styling, new features - is just HTML, JS and
 * CSS. That folder can be replaced at runtime. Only a change to native code
 * needs a real APK: a new plugin, a new Android permission, a different app
 * icon.
 *
 * Which is why this file distinguishes two kinds of update and treats them
 * completely differently:
 *
 *   bundle   downloaded and applied in seconds, no installer, no permission,
 *            no Android dialog. The normal case.
 *   native   a new APK. Rare. Cannot be silent on any unrooted Android - the
 *            system always shows an install confirmation - so the honest thing
 *            is to send the user to the download and say so.
 *
 * Rollback is not an afterthought here. A bad bundle reaches every phone within
 * minutes, so `notifyAppReady()` has to run on every successful start; if it
 * does not, the plugin reverts to the previous bundle on the next launch. That
 * turns "I shipped a white screen to two hundred residents" into "they were
 * briefly on yesterday's build".
 */
import { Capacitor } from '@capacitor/core'

/**
 * Where the manifest lives.
 *
 * Defaults to the origin serving the app, which is right for the web build and
 * for an APK pointed at the same host. Overridable so the bundle can be served
 * from a CDN without rebuilding the API.
 */
const MANIFEST_URL =
  import.meta.env.VITE_UPDATE_URL || '/updates/version.json'

export const isNative = () => Capacitor.isNativePlatform()

async function plugin() {
  const { CapacitorUpdater } = await import('@capgo/capacitor-updater')
  return CapacitorUpdater
}

/**
 * Compare two dotted version strings.
 *
 * Written rather than pulled in, because a comparison this small is easier to
 * read than a dependency, and getting it wrong is loud: it either offers an
 * update that does not exist or hides one that does. Missing parts count as
 * zero, so "1.2" and "1.2.0" are equal rather than one being newer.
 */
export function isNewer(candidate, current) {
  const a = String(candidate || '').split('.').map((n) => parseInt(n, 10) || 0)
  const b = String(current || '').split('.').map((n) => parseInt(n, 10) || 0)
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    const x = a[i] || 0
    const y = b[i] || 0
    if (x !== y) return x > y
  }
  return false
}

/**
 * Mark this bundle as working.
 *
 * Called once from app startup, after React has actually rendered. Everything
 * about rollback hangs off it: the plugin gives a freshly applied bundle a
 * short window to call this, and reverts if it never does. Calling it too early
 * - at module load, say - would mark a bundle healthy that then crashes on its
 * first render, defeating the whole mechanism.
 */
export async function markHealthy() {
  if (!isNative()) return
  try {
    await (await plugin()).notifyAppReady()
  } catch {
    /* Not fatal. Worst case the plugin reverts a bundle that was actually fine,
       which costs the user one relaunch and no data. */
  }
}

/** The bundle and native versions currently running. */
export async function currentVersions() {
  if (!isNative()) {
    return { bundle: import.meta.env.VITE_APP_VERSION || '0.0.0', native: null }
  }
  try {
    const info = await (await plugin()).current()
    return {
      bundle: info?.bundle?.version && info.bundle.version !== 'builtin'
        ? info.bundle.version
        : (import.meta.env.VITE_APP_VERSION || '0.0.0'),
      native: info?.native || null,
    }
  } catch {
    return { bundle: import.meta.env.VITE_APP_VERSION || '0.0.0', native: null }
  }
}

/**
 * Ask the server what the latest version is.
 *
 * Returns null on any failure. An update check is the least important thing the
 * app does - a server hiccup must never stop someone opening their rent page -
 * so every error path here is silence, not an error screen.
 */
export async function checkForUpdate() {
  try {
    const res = await fetch(`${MANIFEST_URL}?t=${Date.now()}`, {
      cache: 'no-store',
    })
    if (!res.ok) return null
    const manifest = await res.json()
    const { bundle, native } = await currentVersions()

    // A native floor the current APK cannot meet. This is the case that saves
    // you when the API changes in a way old clients cannot speak: no bundle can
    // fix a missing plugin, so offering one would be a loop of failed updates.
    const needsApk = Boolean(
      manifest.minNativeVersion
      && native
      && isNewer(String(manifest.minNativeVersion), String(native)),
    )

    return {
      manifest,
      currentBundle: bundle,
      currentNative: native,
      needsApk,
      hasBundleUpdate: Boolean(
        !needsApk && manifest.version && manifest.bundleUrl
        && isNewer(manifest.version, bundle),
      ),
    }
  } catch {
    return null
  }
}

/**
 * Download a bundle and switch to it. The app reloads on success.
 *
 * `onProgress` exists because this runs on Indian mobile data and a frozen
 * button for eight seconds reads as a broken button. The bundle is a few
 * hundred kilobytes, not a game download, but a progress bar is the difference
 * between waiting and giving up.
 */
export async function applyUpdate(manifest, onProgress) {
  if (!isNative()) {
    // The browser updates itself by reloading; there is no bundle to swap.
    window.location.reload()
    return
  }

  const CapacitorUpdater = await plugin()
  let listener = null
  if (onProgress) {
    listener = await CapacitorUpdater.addListener(
      'download', ({ percent }) => onProgress(percent))
  }

  try {
    const bundle = await CapacitorUpdater.download({
      url: manifest.bundleUrl,
      version: manifest.version,
      ...(manifest.checksum ? { checksum: manifest.checksum } : {}),
    })
    // `set` reloads the WebView onto the new bundle. Nothing after it runs.
    await CapacitorUpdater.set({ id: bundle.id })
  } finally {
    listener?.remove?.()
  }
}
