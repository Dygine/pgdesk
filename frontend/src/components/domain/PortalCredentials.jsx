/**
 * App sign-in details for a resident: a QR that works for 30 minutes, plus the
 * temporary password as a fallback.
 *
 * The QR carries a single-use key, never the password. A password cannot
 * expire after thirty minutes - it works until it is changed - so a photo of a
 * password QR forwarded on WhatsApp would be a working login forever. The key
 * dies on first use, after 30 minutes, or when a newer QR is made.
 */
import { useEffect, useState } from 'react'
import { Copy, RefreshCw, Clock3 } from 'lucide-react'
import { Modal, Button, QrCode, InlineAlert } from '@/components/ui'
import { useToast } from '@/context/ToastContext'

function useRemaining(expiresAt) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!expiresAt) return undefined
    setNow(Date.now())
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [expiresAt])
  return expiresAt ? Math.max(0, new Date(expiresAt).getTime() - now) : 0
}

const mmss = (ms) => {
  const s = Math.ceil(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

const STEPS = [
  'Install the PGuru app from get.dygine.com and open it.',
  'Tap “Scan QR code to sign in” and point the camera at this screen.',
  'Choose their own password. That is all.',
]

/**
 * @param credentials { email, temporary_password?, login_code: { payload, expires_at } }
 * @param onRenew     async (current) => next credentials; offered once the QR expires
 */
export function PortalCredentials({ open, onClose, credentials, name, onRenew }) {
  const { success, error } = useToast()
  const [current, setCurrent] = useState(credentials)
  const [renewing, setRenewing] = useState(false)
  useEffect(() => { setCurrent(credentials) }, [credentials])

  const code = current?.login_code
  const left = useRemaining(code?.expires_at)
  const expired = !!code && left <= 0

  if (!current) return null

  const copy = (label, value) => {
    navigator.clipboard?.writeText(value)
    success(`${label} copied`)
  }

  const renew = async () => {
    if (!onRenew) return
    setRenewing(true)
    try {
      setCurrent(await onRenew(current))
    } catch (err) {
      error('Could not make a new QR', err.message)
    } finally { setRenewing(false) }
  }

  return (
    <Modal open={open} onClose={onClose} size="sm" title="App sign-in"
      subtitle={name ? `For ${name}` : undefined}
      footer={<Button variant="primary" onClick={onClose}>Done</Button>}>
      <div className="space-y-5">
        {code && (
          <div className="flex flex-col items-center text-center">
            <div className="relative rounded-xl border border-line p-2 bg-white">
              <QrCode value={code.payload} size={208} alt="Sign-in QR code"
                className={expired ? 'opacity-20 blur-[2px]' : ''} />
              {expired && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6">
                  <p className="text-sm font-semibold text-slate-900">This QR has expired</p>
                  {onRenew && (
                    <Button size="sm" variant="primary" icon={RefreshCw} loading={renewing}
                      onClick={renew}>Make a new QR</Button>
                  )}
                </div>
              )}
            </div>
            <p className={`mt-3 inline-flex items-center gap-1.5 text-sm tnum ${
              expired ? 'text-rose-600' : left < 5 * 60 * 1000 ? 'text-amber-700' : 'text-slate-600'}`}>
              <Clock3 size={14} />
              {expired ? 'Expired' : `Works for ${mmss(left)} · one scan only`}
            </p>
          </div>
        )}

        <ol className="space-y-2">
          {STEPS.map((step, i) => (
            <li key={step} className="flex gap-2.5 text-sm text-slate-700">
              <span className="h-5 w-5 shrink-0 rounded-full bg-brand-50 text-brand-700 text-2xs font-semibold inline-flex items-center justify-center tnum">
                {i + 1}
              </span>
              <span>{step}</span>
            </li>
          ))}
        </ol>

        {(current.email || current.temporary_password) && (
          <div className="rounded-lg border border-line bg-slate-50 p-3.5 space-y-2">
            <p className="text-xs text-slate-500">No camera? They can sign in with:</p>
            {[['Email', current.email], ['Password', current.temporary_password]]
              .filter(([, v]) => v).map(([label, value]) => (
                <div key={label} className="flex items-center justify-between gap-3">
                  <span className="text-xs text-slate-500">{label}</span>
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-sm text-slate-900 truncate">{value}</span>
                    <button type="button" aria-label={`Copy ${label}`} onClick={() => copy(label, value)}
                      className="text-slate-400 hover:text-slate-700 shrink-0"><Copy size={14} /></button>
                  </span>
                </div>
              ))}
          </div>
        )}
        {current.temporary_password && (
          <InlineAlert tone="warn">
            The password is shown only now. It is stored as a hash and cannot be looked
            up again, and the QR never contains it.
          </InlineAlert>
        )}
      </div>
    </Modal>
  )
}
