/**
 * Where a PG seeker's session lives on the device.
 *
 * A seeker token is deliberately low-power: the API accepts it only on
 * /public/seeker/*, where it can send enquiries and read the seeker's own
 * enquiries back - never tenant data (see backend app/models/seeker.py). That
 * is why plain app storage is acceptable here, unlike the staff/resident
 * refresh token, which stays in an HttpOnly cookie on the web.
 *
 * Native: Capacitor Preferences (the app's private sandbox). Web: localStorage.
 */
import { Capacitor } from '@capacitor/core'

const KEY = 'pgdesk.seeker'

// Never return the plugin object from an async function - see nativeSession.js.
const loadPreferences = () => import('@capacitor/preferences')

export async function readSeekerToken() {
  try {
    if (Capacitor.isNativePlatform()) {
      const { Preferences } = await loadPreferences()
      const { value } = await Preferences.get({ key: KEY })
      return value || null
    }
    return window.localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export async function writeSeekerToken(token) {
  try {
    if (Capacitor.isNativePlatform()) {
      const { Preferences } = await loadPreferences()
      if (token) await Preferences.set({ key: KEY, value: token })
      else await Preferences.remove({ key: KEY })
      return
    }
    if (token) window.localStorage.setItem(KEY, token)
    else window.localStorage.removeItem(KEY)
  } catch {
    // Storage blocked or full: they stay signed in until the app closes.
  }
}
