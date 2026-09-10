/**
 * Keeping every screen on the latest version.
 *
 * The Android app no longer carries its own copy of the screens. It opens
 * https://pgdesk.dygine.com inside the app (capacitor.config.json, server.url),
 * exactly like a browser does. So deploying the website IS the update, for the
 * browser and the app alike: git push, Render rebuilds the site, and the next
 * time anything loads, it gets the new version. There is no bundle to publish,
 * no version number to bump and nothing to download.
 *
 * (It used to be different: the APK held a frozen copy of the screens and
 * looked for updates at a relative /updates/version.json - which, inside the
 * app, meant its own files. So an installed app never saw a single update.)
 *
 * The one gap left is a screen that is already open when a deploy lands. This
 * notices it: it re-reads index.html from the server and compares the
 * JavaScript bundle it names with the one this page is running. Different
 * means something newer is live, and the banner offers a reload. Nothing
 * reloads on its own - someone may be halfway through typing a payment UTR.
 */
const bundleOf = (src) => (src ? new URL(src, window.location.href).pathname : null)

/** The hashed bundle this page was started from. Null on the dev server. */
const RUNNING = typeof document === 'undefined' ? null : bundleOf(
  document.querySelector('script[type="module"][src*="/assets/index-"]')?.getAttribute('src'))

export async function newVersionAvailable() {
  if (!RUNNING) return false
  try {
    const res = await fetch(`${window.location.origin}/?v=${Date.now()}`, {
      cache: 'no-store', credentials: 'omit',
    })
    if (!res.ok) return false
    const found = (await res.text()).match(/src="([^"]*\/assets\/index-[^"]+\.js)"/)
    return Boolean(found) && bundleOf(found[1]) !== RUNNING
  } catch {
    return false        // offline or mid-deploy: ask again later
  }
}

export function reloadToLatest() {
  window.location.reload()
}
