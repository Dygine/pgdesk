import { useEffect, useState } from 'react'
import { Capacitor } from '@capacitor/core'
import {
  Bell, MapPin, Camera, Check, ChevronRight, ShieldCheck,
} from 'lucide-react'
import { Card, Button, InlineAlert } from '@/components/ui'

/**
 * Asking for permissions, once, with reasons.
 *
 * The obvious approach - fire all three prompts on first launch - loses. On
 * Android a second denial is permanent: the system stops showing the prompt
 * entirely, forever, and the feature silently never works again. The user gets
 * a scanner that does nothing and no way to find out why, and you get a support
 * call you cannot diagnose.
 *
 * So each one is explained before it is asked, and asked on its own. Same three
 * permissions, far higher acceptance, and anyone who says no can turn it on
 * later from Settings rather than being stuck.
 *
 * Shown once, tracked in Preferences. Native only - a browser prompts at the
 * moment of use and has no equivalent of a permanent denial.
 */
const STORAGE_KEY = 'pgdesk.permissions.asked'

const ITEMS = [
  {
    key: 'notifications',
    icon: Bell,
    title: 'Notifications',
    why: 'Rent reminders, announcements from your PG, and replies to anything you ask.',
    async request() {
      const { LocalNotifications } = await import('@capacitor/local-notifications')
      const res = await LocalNotifications.requestPermissions()
      return res.display
    },
  },
  {
    key: 'location',
    icon: MapPin,
    title: 'Location',
    why: 'Used only when you check in at the gate, to confirm you are actually there. '
       + 'Never tracked in the background.',
    async request() {
      const { Geolocation } = await import('@capacitor/geolocation')
      const res = await Geolocation.requestPermissions()
      return res.location
    },
  },
  {
    key: 'camera',
    icon: Camera,
    title: 'Camera',
    why: 'For scanning the QR code at the gate. Nothing is photographed or stored.',
    async request() {
      const { BarcodeScanner } = await import('@capacitor-mlkit/barcode-scanning')
      const res = await BarcodeScanner.requestPermissions()
      return res.camera
    },
  },
]

export function PermissionOnboarding({ onDone }) {
  const [index, setIndex] = useState(0)
  const [results, setResults] = useState({})
  const [busy, setBusy] = useState(false)

  const item = ITEMS[index]
  const finished = index >= ITEMS.length

  useEffect(() => {
    if (!finished) return
    ;(async () => {
      try {
        const { Preferences } = await import('@capacitor/preferences')
        await Preferences.set({ key: STORAGE_KEY, value: '1' })
      } catch { /* not worth blocking on */ }
      onDone?.(results)
    })()
  }, [finished, results, onDone])

  const ask = async () => {
    setBusy(true)
    try {
      const outcome = await item.request()
      setResults((r) => ({ ...r, [item.key]: outcome }))
    } catch {
      setResults((r) => ({ ...r, [item.key]: 'denied' }))
    } finally {
      setBusy(false)
      setIndex((i) => i + 1)
    }
  }

  const skip = () => {
    setResults((r) => ({ ...r, [item.key]: 'skipped' }))
    setIndex((i) => i + 1)
  }

  if (finished) return null

  const Icon = item.icon

  return (
    <div className="fixed inset-0 z-[60] bg-slate-900/90 flex items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <div className="p-6">
          <div className="flex items-center gap-1.5 mb-6">
            {ITEMS.map((it, i) => (
              <span key={it.key}
                className={`h-1 flex-1 rounded-full ${
                  i < index ? 'bg-brand-600' : i === index ? 'bg-brand-300' : 'bg-slate-200'}`} />
            ))}
          </div>

          <span className="h-12 w-12 rounded-2xl bg-brand-50 text-brand-700
                           inline-flex items-center justify-center mb-3">
            <Icon size={22} />
          </span>

          <h2 className="text-base font-semibold text-slate-900">{item.title}</h2>
          <p className="text-sm text-slate-500 mt-1.5">{item.why}</p>

          <Button variant="primary" className="w-full mt-6" loading={busy}
            iconRight={ChevronRight} onClick={ask}>
            Allow {item.title.toLowerCase()}
          </Button>

          <button type="button" onClick={skip} disabled={busy}
            className="w-full text-xs text-slate-500 hover:text-slate-800 mt-3">
            Not now
          </button>

          <p className="text-2xs text-slate-400 text-center mt-4">
            You can change any of these later in Settings.
          </p>
        </div>
      </Card>
    </div>
  )
}

/**
 * Whether to show it at all.
 *
 * Never on the web, and never twice. Returns false on any error so a broken
 * Preferences call cannot trap someone behind a permission wall on every
 * single launch.
 */
export async function shouldAskPermissions() {
  if (!Capacitor.isNativePlatform()) return false
  try {
    const { Preferences } = await import('@capacitor/preferences')
    const { value } = await Preferences.get({ key: STORAGE_KEY })
    return value !== '1'
  } catch {
    return false
  }
}

/** Re-runs the flow from a Settings screen, for anyone who said no. */
export async function resetPermissionOnboarding() {
  try {
    const { Preferences } = await import('@capacitor/preferences')
    await Preferences.remove({ key: STORAGE_KEY })
  } catch { /* nothing to undo */ }
}

export { ShieldCheck, Check }
