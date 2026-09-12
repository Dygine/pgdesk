/**
 * Telling an old app that it is an old app.
 *
 * The problem this solves is structural, not cosmetic. `server.url` is compiled
 * into the APK at build time, so an installed app will load
 * https://pgdesk.dygine.com for as long as it exists, no matter what is
 * deployed. New APKs point at pgguru.in; the ones already on phones never will.
 *
 * So the old domain cannot simply be switched off - doing that bricks every
 * installed app at once, with no route back except "uninstall and reinstall",
 * delivered to people who by then cannot open the app to read the instruction.
 *
 * Instead the old domain stays alive and the app that loads from it says so.
 * This banner appears only when the page was served from a retired host, and
 * only inside the native app - a browser on the old address just works and has
 * nothing to migrate.
 *
 * Dismissal lasts three days rather than forever. This is not a newsletter
 * prompt; it is the difference between a working app and a broken one in a few
 * months' time, and someone who taps "later" on a Tuesday should be asked again
 * on Friday.
 *
 * When the old domain is finally retired, delete this file and the entry in
 * RETIRED_HOSTS. Until then it is what makes retiring it safe.
 */
import { useEffect, useState } from 'react'
import { Download, X, AlertTriangle } from 'lucide-react'
import { isNativeApp } from '@/lib/nativeSession'

/** Hosts that still serve the app but are on their way out. */
const RETIRED_HOSTS = ['pgdesk.dygine.com', 'get.dygine.com']
const HOME = 'https://pgguru.in'
const SNOOZE_KEY = 'pgguru.legacyDomain.snoozed'
const SNOOZE_DAYS = 3

function snoozed() {
  try {
    const at = Number(window.localStorage.getItem(SNOOZE_KEY) || 0)
    return at > 0 && Date.now() - at < SNOOZE_DAYS * 24 * 60 * 60 * 1000
  } catch { return false }
}

export function LegacyDomainBanner() {
  const [show, setShow] = useState(false)

  useEffect(() => {
    if (!isNativeApp()) return                       // a browser has nothing to move
    if (!RETIRED_HOSTS.includes(window.location.hostname)) return
    if (snoozed()) return
    setShow(true)
  }, [])

  if (!show) return null

  const later = () => {
    try { window.localStorage.setItem(SNOOZE_KEY, String(Date.now())) } catch { /* ignore */ }
    setShow(false)
  }

  return (
    <div className="bg-accent-50 border-b border-accent-200 px-4 py-3 safe-t">
      <div className="max-w-3xl mx-auto flex items-start gap-3">
        <AlertTriangle size={18} className="text-accent-700 shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-accent-900">Update your app</p>
          <p className="text-xs text-accent-800/90 mt-0.5 leading-relaxed">
            This copy still loads from our old address. Download the new one from
            pgguru.in — you stay signed in and nothing is lost.
          </p>
          <div className="mt-2.5 flex flex-wrap gap-2">
            <a href={`${HOME}/pgguru.apk`}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-accent-500 px-3 text-xs font-semibold text-white hover:bg-accent-600">
              <Download size={13} /> Download
            </a>
            <button type="button" onClick={later}
              className="inline-flex h-8 items-center rounded-lg border border-accent-300 px-3 text-xs font-medium text-accent-800 hover:bg-accent-100">
              Later
            </button>
          </div>
        </div>
        <button type="button" onClick={later} aria-label="Dismiss"
          className="h-7 w-7 shrink-0 inline-flex items-center justify-center rounded-lg text-accent-700 hover:bg-accent-100">
          <X size={15} />
        </button>
      </div>
    </div>
  )
}
