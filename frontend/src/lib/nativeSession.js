/**
 * Keeping the app signed in.
 *
 * On the web the refresh token lives in an HttpOnly cookie and JavaScript never
 * touches it. That is the right design there and it does not change.
 *
 * Inside the Android app it cannot work at all. The WebView serves the bundle
 * from https://localhost while the API is on another domain, so every call is
 * cross-site, and a SameSite=Lax cookie is simply not attached to a cross-site
 * request. The session would die about thirty minutes after login with no
 * visible cause and no error to search for.
 *
 * So on native the app holds the refresh token itself, in Capacitor Preferences
 * — Android SharedPreferences underneath, inside the app's private sandbox,
 * which no other app can read. Combined with a ten-year token from the server,
 * that is "signed in until you remove the app".
 *
 * The honest trade: this token is readable by anything with root on the device
 * or by the app's own JavaScript, where the cookie was not. In a Capacitor app
 * the bundle is fixed at build time and loads no third-party scripts, so the
 * XSS route the HttpOnly cookie defends against is largely closed by
 * construction. On the web, where that is not true, the cookie stays.
 *
 * Nothing here survives "Clear storage" in Android settings — that wipes the
 * app sandbox, which is the same thing an uninstall does. No app can survive
 * it, and one that could would be storing credentials somewhere it should not.
 */
import { Capacitor } from '@capacitor/core'

const KEY = 'pgdesk.refresh'

export const isNativeApp = () => Capacitor.isNativePlatform()

/** Tells the API to issue a long session and hand the token back. */
export const NATIVE_CLIENT_HEADER = 'X-PGDesk-Client'

/**
 * Never `return` a Capacitor plugin object from an `async` function.
 *
 * Async functions resolve their return value, and resolution checks for a
 * `.then` property. A Capacitor plugin is a proxy where *every* property access
 * yields a method stub, so `.then` looks callable. JavaScript calls it believing
 * it is resolving a promise; Capacitor throws "not implemented" and never
 * invokes the resolve or reject callback it was handed - so the awaiting promise
 * settles never, not late.
 *
 * The symptom is an app frozen on its loading screen with one console line and
 * no stack. Import the module and use the plugin in the same function instead.
 */
const loadPreferences = () => import('@capacitor/preferences')

export async function readRefreshToken() {
  if (!isNativeApp()) return null
  try {
    const { Preferences } = await loadPreferences()
    const { value } = await Preferences.get({ key: KEY })
    return value || null
  } catch {
    return null
  }
}

export async function writeRefreshToken(token) {
  if (!isNativeApp()) return
  try {
    const { Preferences } = await loadPreferences()
    if (token) await Preferences.set({ key: KEY, value: token })
    else await Preferences.remove({ key: KEY })
  } catch {
    // A failed write means this session ends when the app closes. Worth not
    // crashing over: the user is signed in right now either way, and the next
    // successful login will store one.
  }
}

export async function clearRefreshToken() {
  await writeRefreshToken(null)
}
