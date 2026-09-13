/**
 * Push notifications on the installed app.
 *
 * What this file does and does not do
 * -----------------------------------
 * It does not draw anything. When the app is closed, Android draws the
 * notification from the payload the server sent, and no JavaScript of ours is
 * running at all. This file handles the three moments that surround that:
 * getting a token, giving it to the server, and routing when the notification
 * is tapped.
 *
 * Why the token is sent on every start
 * ------------------------------------
 * Firebase rotates a registration token on its own schedule - a reinstall, a
 * restore from backup, a long enough gap between opens. A token fetched once
 * and cached for ever quietly stops working, and the symptom is silence:
 * nothing errors, notifications simply stop, and nobody reports it as a bug
 * because nothing visibly broke. Re-registering on every start costs one
 * request and removes the whole class of failure.
 *
 * Why permission is not requested here
 * ------------------------------------
 * `PermissionOnboarding` asks, with a reason, one prompt at a time. On Android
 * a second denial is permanent - the system stops showing the prompt for ever -
 * so firing `requestPermissions` cold at startup buys a denial that can never
 * be undone from inside the app. This module only registers when permission has
 * already been granted.
 */
import { Capacitor } from '@capacitor/core'

/** The API client is injected so this module does not import the auth session. */
let apiPost = null
let navigate = null

const isNative = () => Capacitor.isNativePlatform()

/** Remembered so sign-out can tell the server to stop sending to this phone. */
const TOKEN_KEY = 'pgguru.push.token'

async function rememberToken(token) {
  try {
    const { Preferences } = await import('@capacitor/preferences')
    await Preferences.set({ key: TOKEN_KEY, value: token })
  } catch {
    /* Preferences unavailable on web - nothing to remember there. */
  }
}

async function recallToken() {
  try {
    const { Preferences } = await import('@capacitor/preferences')
    const { value } = await Preferences.get({ key: TOKEN_KEY })
    return value || null
  } catch {
    return null
  }
}

/**
 * Whether this phone has already agreed to notifications.
 *
 * Checked rather than requested: see the note above about permanent denial.
 */
export async function hasPushPermission() {
  if (!isNative()) return false
  try {
    const { PushNotifications } = await import('@capacitor/push-notifications')
    const status = await PushNotifications.checkPermissions()
    return status.receive === 'granted'
  } catch {
    return false
  }
}

/**
 * Ask for permission. Called only by the onboarding screen, which explains why
 * first.
 */
export async function requestPushPermission() {
  if (!isNative()) return 'denied'
  const { PushNotifications } = await import('@capacitor/push-notifications')
  const status = await PushNotifications.requestPermissions()
  return status.receive
}

let listenersAttached = false

/**
 * Register this phone with Firebase and hand the token to the server.
 *
 * Safe to call repeatedly - listeners are attached once, and the server treats
 * a repeat registration as a refresh rather than a new device.
 */
export async function registerForPush({ post, onNavigate } = {}) {
  if (post) apiPost = post
  if (onNavigate) navigate = onNavigate

  if (!isNative()) return { ok: false, reason: 'not a native app' }
  if (!(await hasPushPermission())) return { ok: false, reason: 'no permission' }

  const { PushNotifications } = await import('@capacitor/push-notifications')

  if (!listenersAttached) {
    listenersAttached = true

    // Firebase hands the token back asynchronously, through this event - there
    // is no promise that resolves with it. Registration is therefore two
    // steps: call register(), then wait to be told.
    await PushNotifications.addListener('registration', async (token) => {
      await rememberToken(token.value)
      if (!apiPost) return
      try {
        await apiPost('/notifications/device', {
          token: token.value,
          platform: Capacitor.getPlatform() === 'ios' ? 'ios' : 'android',
        })
      } catch {
        // Offline, or the session has not been established yet. The next app
        // start re-registers, so a failure here costs one cycle rather than
        // leaving the phone permanently unreachable.
      }
    })

    await PushNotifications.addListener('registrationError', (err) => {
      // Almost always one of two things: google-services.json missing from the
      // build, or its package name not matching applicationId. Logged plainly
      // because both are invisible at runtime otherwise.
      console.warn('Push registration failed:', err?.error)
    })

    // Tapped while the app was closed or in the background. The server puts the
    // destination in `data.link`, which is the same link the in-app
    // notification list uses - one source of truth for where a notification
    // goes.
    await PushNotifications.addListener(
      'pushNotificationActionPerformed',
      (action) => {
        const link = action?.notification?.data?.link
        if (link && navigate) navigate(link)
      },
    )

    // Arrived while the app was open and in the foreground. Deliberately not
    // turned into a popup: the user is already looking at the app, and the
    // notification bell updates on its own. A banner over the screen they are
    // typing into is an interruption, not a service.
    await PushNotifications.addListener('pushNotificationReceived', () => {
      window.dispatchEvent(new CustomEvent('pgguru:notification'))
    })
  }

  await PushNotifications.register()
  return { ok: true }
}

/**
 * Stop notifications to this phone. Called on sign-out.
 *
 * Without this the next person to sign in on the same handset keeps receiving
 * the previous one's rent reminders until Firebase happens to rotate the token,
 * which can be months.
 */
export async function unregisterFromPush({ post } = {}) {
  if (!isNative()) return
  const token = await recallToken()
  if (!token) return
  try {
    await (post || apiPost)?.('/notifications/device/revoke', { token })
  } catch {
    /* Signing out must never fail because the network is down. */
  }
}
