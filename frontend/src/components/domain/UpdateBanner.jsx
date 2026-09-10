import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, X } from 'lucide-react'
import { newVersionAvailable, reloadToLatest } from '@/lib/liveUpdate'
import { Button } from '@/components/ui'

/** How often an open screen asks whether a newer version has been deployed. */
const CHECK_EVERY_MS = 10 * 60 * 1000

/**
 * "A new version is ready - Reload".
 *
 * The browser and the Android app both load the live site, so a fresh open
 * always gets the latest version. This is only for a screen that was already
 * open when a deploy landed. It asks when the app comes back to the front,
 * when a browser tab becomes visible again, and every ten minutes - and it
 * offers, never forces, because a reload in the middle of a form loses it.
 */
export function UpdateBanner() {
  const [ready, setReady] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  const check = useCallback(async () => {
    if (document.visibilityState === 'hidden') return
    if (await newVersionAvailable()) setReady(true)
  }, [])

  useEffect(() => {
    const onVisible = () => { if (document.visibilityState === 'visible') check() }
    window.addEventListener('pgdesk:resume', check)
    document.addEventListener('visibilitychange', onVisible)
    const timer = setInterval(check, CHECK_EVERY_MS)
    return () => {
      window.removeEventListener('pgdesk:resume', check)
      document.removeEventListener('visibilitychange', onVisible)
      clearInterval(timer)
    }
  }, [check])

  if (!ready || dismissed) return null
  return (
    <div role="status" aria-live="polite"
      className="fixed z-[70] inset-x-3 bottom-20 sm:bottom-6 sm:left-auto sm:right-6 sm:w-[24rem] card shadow-pop animate-popIn safe-b">
      <div className="flex items-center gap-3 p-3.5">
        <span className="h-9 w-9 rounded-lg bg-brand-50 text-brand-700 inline-flex items-center justify-center shrink-0">
          <RefreshCw size={17} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-900">A new version of PGDesk is ready</p>
          <p className="text-xs text-slate-500">Reload to get the latest screens.</p>
        </div>
        <Button size="sm" variant="primary" onClick={reloadToLatest}>Reload</Button>
        <button onClick={() => setDismissed(true)} aria-label="Later"
          className="text-slate-400 hover:text-slate-700 p-1 shrink-0"><X size={15} /></button>
      </div>
    </div>
  )
}
