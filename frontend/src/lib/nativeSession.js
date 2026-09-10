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

async function prefs() {
  const { Preferences } = await import('@capacitor/preferences')
  return Preferences
}

export async function readRefreshToken() {
  if (!isNativeApp()) return null
  try {
    const { value } = await (await prefs()).get({ key: KEY })
    return value || null
  } catch {
    return null
  }
}

export async function writeRefreshToken(token) {
  if (!isNativeApp()) return
  try {
    if (token) await (await prefs()).set({ key: KEY, value: token })
    else await (await prefs()).remove({ key: KEY })
  } catch {
    // A failed write means this session ends when the app closes. Worth not
    // crashing over: the user is signed in right now either way, and the next
    // successful login will store one.
  }
}

export async function clearRefreshToken() {
  await writeRefreshToken(null)
}
