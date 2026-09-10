import { useCallback, useEffect, useState } from 'react'
import { Download, RefreshCw, X, TriangleAlert } from 'lucide-react'
import {
  applyUpdate, checkForUpdate, isNative, markHealthy,
} from '@/lib/liveUpdate'
import { Button, Card, ProgressBar } from '@/components/ui'

/**
 * "Update available", and occasionally "you must update".
 *
 * Checked when the app opens and again when it returns from the background,
 * which is what every app people are used to does. A background timer would be
 * worse on both counts: it drains battery, and Xiaomi and Oppo kill background
 * work aggressively enough that it would not run reliably anyway.
 *
 * Two states, and the difference matters:
 *
 *   banner   a newer bundle exists. Dismissible, because someone in the middle
 *            of recording a payment should not be interrupted.
 *   gate     this APK is too old for the current API. Not dismissible, because
 *            letting them past would mean a screen of failing requests they
 *            cannot diagnose - the block is kinder than the mystery.
 */
export function UpdateBanner() {
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const [percent, setPercent] = useState(0)
  const [dismissed, setDismissed] = useState(false)

  const check = useCallback(async () => {
    const result = await checkForUpdate()
    if (result && (result.hasBundleUpdate || result.needsApk)) setState(result)
    else setState(null)
  }, [])

  useEffect(() => {
    // Tell the updater this bundle starts cleanly. Anything that reaches here
    // has already rendered, which is the property rollback depends on.
    markHealthy()
    check()

    // AppShell already dispatches this when the app comes back from the
    // background, so the check rides on an event that exists rather than
    // adding a second lifecycle listener.
    const onResume = () => check()
    window.addEventListener('pgdesk:resume', onResume)
    return () => window.removeEventListener('pgdesk:resume', onResume)
  }, [check])

  const update = async () => {
    setBusy(true)
    setPercent(0)
    try {
      await applyUpdate(state.manifest, setPercent)
      // Unreachable on native: `set` reloads the WebView.
    } catch {
      setBusy(false)
      // Left on screen deliberately. A failed download is usually a dropped
      // connection, and the useful next step is trying again, not an error
      // dialog that removes the button.
    }
  }

  if (!state) return null

  /* ------------------------------------------------- must install a new APK */
  if (state.needsApk) {
    const url = state.manifest.nativeUrl
    return (
      <div className="fixed inset-0 z-[60] bg-slate-900/90 flex items-center justify-center p-4">
        <Card className="w-full max-w-sm">
          <div className="p-6 text-center">
            <span className="h-12 w-12 rounded-2xl bg-amber-50 text-amber-600
                             inline-flex items-center justify-center mb-3">
              <TriangleAlert size={22} />
            </span>
            <h2 className="text-base font-semibold text-slate-900">
              A new version is required
            </h2>
            <p className="text-sm text-slate-500 mt-1.5">
              {state.manifest.notes
                || 'This version of the app can no longer talk to the server. '
                   + 'Please install the latest one to continue.'}
            </p>
            <p className="text-2xs text-slate-400 mt-3 tnum">
              Installed {state.currentNative} · required {state.manifest.minNativeVersion}
            </p>

            {url ? (
              <a href={url} className="block mt-5">
                <Button variant="primary" icon={Download} className="w-full">
                  Download the update
                </Button>
              </a>
            ) : (
              <p className="text-xs text-slate-500 mt-5">
                Contact your PG for the latest version.
              </p>
            )}
            {/* Android always shows its own install confirmation, on every
                device, for every app that is not a system installer. Saying so
                here stops the tap looking like it failed. */}
            <p className="text-2xs text-slate-400 mt-3">
              Android will ask you to confirm the install.
            </p>
          </div>
        </Card>
      </div>
    )
  }

  /* ----------------------------------------------------- bundle update ready */
  if (dismissed) return null

  return (
    <div className="sticky top-0 z-40 px-3 pt-3">
      <div className="rounded-xl border border-brand-200 bg-brand-50 p-3
                      flex items-center gap-3">
        <span className="h-9 w-9 rounded-lg bg-white text-brand-700
                         inline-flex items-center justify-center shrink-0">
          <RefreshCw size={16} className={busy ? 'animate-spin' : undefined} />
        </span>

        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-900">
            {busy ? 'Updating…' : 'Update available'}
          </p>
          {busy ? (
            <ProgressBar value={percent} max={100} className="mt-1.5" />
          ) : (
            <p className="text-xs text-slate-600 truncate">
              {state.manifest.notes || `Version ${state.manifest.version} is ready.`}
            </p>
          )}
        </div>

        {!busy && (
          <>
            <Button size="sm" variant="primary" onClick={update}>Update</Button>
            <button type="button" onClick={() => setDismissed(true)}
              aria-label="Not now"
              className="h-8 w-8 inline-flex items-center justify-center rounded-lg
                         text-slate-500 hover:bg-white/70 shrink-0">
              <X size={15} />
            </button>
          </>
        )}
      </div>
      {/* Only shown on a phone. In a browser "update" is just a reload, and
          promising a download there would be a lie. */}
      {!isNative() && !busy && (
        <p className="text-2xs text-slate-400 mt-1 px-1">
          Reloads the page with the newest version.
        </p>
      )}
    </div>
  )
}
