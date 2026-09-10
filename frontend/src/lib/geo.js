/**
 * Where the phone thinks it is.
 *
 * Wraps Capacitor Geolocation, which uses the platform API on Android and
 * `navigator.geolocation` in a browser, so there is one code path rather than
 * two that drift.
 *
 * The awkward part of geolocation is not getting a position, it is getting a
 * position good enough to decide something with. A cold GPS indoors returns
 * quickly and confidently with an accuracy of several hundred metres, which is
 * worse than useless for a 150 metre fence: it is wrong in a way that looks
 * right. So this module reports `accuracy` everywhere and never hides it.
 */
import { Capacitor } from '@capacitor/core'

const isNative = () => Capacitor.isNativePlatform()

/** Human-readable reason a position could not be read. */
export class LocationError extends Error {
  constructor(code, message) {
    super(message)
    this.code = code
  }
}

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
const loadGeolocation = () => import('@capacitor/geolocation')

/**
 * Ask for permission, returning what the user chose rather than throwing.
 *
 * A denial is a normal outcome that the screen has to explain, not an
 * exception. On the web the prompt only appears when a position is actually
 * requested, so this resolves optimistically there and the real answer arrives
 * from `currentPosition`.
 */
export async function requestPermission() {
  try {
    if (!isNative()) return 'prompt'
    const { Geolocation } = await loadGeolocation()
    const status = await Geolocation.requestPermissions()
    return status.location ?? 'denied'
  } catch {
    return 'denied'
  }
}

/**
 * One position fix.
 *
 * `enableHighAccuracy` is on because the coarse network fix is routinely a
 * kilometre out in Indian cities, which no usable radius can absorb. The
 * timeout is generous for the same reason - a first GPS fix outdoors takes
 * real seconds, and failing at three of them just makes the button feel broken.
 *
 * `maximumAge` is zero deliberately. A cached fix from when the resident was at
 * college would happily pass a geofence check.
 */
export async function currentPosition({ timeout = 15000 } = {}) {
  let Geolocation
  try {
    ;({ Geolocation } = await loadGeolocation())
  } catch {
    throw new LocationError('unsupported', 'Location is not available on this device.')
  }

  try {
    const pos = await Geolocation.getCurrentPosition({
      enableHighAccuracy: true, timeout, maximumAge: 0,
    })
    return {
      latitude: pos.coords.latitude,
      longitude: pos.coords.longitude,
      accuracy: pos.coords.accuracy ?? null,
      at: pos.timestamp,
    }
  } catch (err) {
    const raw = String(err?.message || err || '').toLowerCase()
    if (raw.includes('denied') || raw.includes('permission')) {
      throw new LocationError(
        'denied',
        'Location permission is off. Allow it for PGDesk, then try again.')
    }
    if (raw.includes('timeout') || raw.includes('timed out')) {
      throw new LocationError(
        'timeout',
        'Could not get a GPS fix. Step outside or near a window and try again.')
    }
    if (raw.includes('unavailable') || raw.includes('disabled')) {
      throw new LocationError(
        'off', 'Turn on location (GPS) on your phone, then try again.')
    }
    throw new LocationError('failed', 'Could not read your location.')
  }
}

/** Metres, rounded the way a person would say it. */
export function formatDistance(metres) {
  if (metres == null) return '—'
  if (metres < 1000) return `${Math.round(metres)} m`
  return `${(metres / 1000).toFixed(1)} km`
}
