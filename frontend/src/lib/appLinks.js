/**
 * Whether an APK download link may be shown.
 *
 * Google Play's Device and Network Abuse policy forbids an app distributed
 * through Play from offering, linking to, or installing an APK obtained
 * anywhere else. The Android build is a WebView over pgguru.in, so every page
 * of this site - including the marketing pages - is *inside* the published
 * app. A "Download for Android" button on the public home page is therefore a
 * policy violation the moment the app is listed, even though it is perfectly
 * correct in a browser.
 *
 * The rule is the same everywhere, so it lives in one function rather than in
 * a condition copied into each call site and forgotten in the next one.
 *
 * The site content is editable from master admin, so the href cannot be
 * trusted to keep any particular shape: the check is on the link, not on the
 * component that renders it.
 */
import { Capacitor } from '@capacitor/core'

/** True when this href points at an installable Android package. */
export function isApkLink(href) {
  return typeof href === 'string' && href.toLowerCase().includes('.apk')
}

/** True when this app is the installed Android build rather than a browser. */
export function isNativeBuild() {
  try {
    return Capacitor.isNativePlatform()
  } catch {
    // Capacitor is absent in a plain browser bundle and in tests. Absent means
    // "not native", which is the safe answer: it only ever permits a link that
    // a browser is allowed to show anyway.
    return false
  }
}

/**
 * May this href be rendered here?
 *
 * Everything that is not an APK link is always allowed. An APK link is allowed
 * in a browser and never inside the installed app.
 */
export function mayShowLink(href) {
  return !isApkLink(href) || !isNativeBuild()
}
