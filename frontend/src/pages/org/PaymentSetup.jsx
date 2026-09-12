/**
 * How residents pay this PG - the owner's side.
 *
 * Three ways, any combination:
 *   Razorpay       residents pay by card/UPI/net banking in the app; confirmed
 *                  automatically by Razorpay's signature. Needs the PG's own keys.
 *   UPI            the app draws a UPI QR with the amount filled in; the resident
 *                  types the 12-digit UTR and the payment waits for verification.
 *   Bank transfer  account details shown; UTR required; waits for verification.
 *
 * The Razorpay key secret and webhook secret are write-only - the same rule as
 * the platform's email key. The screen can say "saved", never show them.
 */
import { useEffect, useState } from 'react'
import { Save, Smartphone, Copy, PlugZap, ImagePlus, Trash2 } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { paymentSettingsApi } from '@/services/api/paymentSettingsApi'
import { BASE_URL } from '@/services/api/client'
import { useToast } from '@/context/ToastContext'
import {
  Card, CardHeader, Button, FormField, Input, Textarea, Toggle, InlineAlert, Skeleton, StatusBadge,
} from '@/components/ui'

const KEEP = ''

async function shrinkImage(file) {
  const url = URL.createObjectURL(file)
  try {
    const img = await new Promise((resolve, reject) => {
      const i = new Image(); i.onload = () => resolve(i); i.onerror = reject; i.src = url
    })
    const scale = Math.min(1, 640 / Math.max(img.width, img.height))
    const c = document.createElement('canvas')
    c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale)
    const ctx = c.getContext('2d')
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height)
    ctx.drawImage(img, 0, 0, c.width, c.height)
    // PNG keeps a QR code crisp; a phone photo of a standee is smaller as JPEG.
    const png = c.toDataURL('image/png')
    return png.length < 350_000 ? png : c.toDataURL('image/jpeg', 0.85)
  } finally { URL.revokeObjectURL(url) }
}

export default function PaymentSetup() {
  const { can } = useAuth()
  const { success, error } = useToast()
  const settings = useApi(() => paymentSettingsApi.get(), [], { enabled: can('settings.view') })
  const [f, setF] = useState(null)
  const [secret, setSecret] = useState(KEEP)
  const [hook, setHook] = useState(KEEP)
  const [busy, setBusy] = useState(false)
  const [testing, setTesting] = useState(false)
  const manage = can('settings.manage')

  useEffect(() => { if (settings.data) setF({ ...settings.data }) }, [settings.data])
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e?.target ? e.target.value : e }))

  if (settings.error) return <InlineAlert tone="error" title="Could not load">{settings.error.message}</InlineAlert>
  if (!f) return <Skeleton className="h-96" />

  const webhookUrl = `${BASE_URL.replace(/\/$/, '')}${f.webhook_path}`

  const save = async () => {
    setBusy(true)
    try {
      const body = {
        razorpay_enabled: !!f.razorpay_enabled, razorpay_key_id: f.razorpay_key_id || '',
        upi_enabled: !!f.upi_enabled, upi_id: f.upi_id || '', upi_payee_name: f.upi_payee_name || '',
        qr_image: f.qr_image || '', bank_enabled: !!f.bank_enabled,
        bank_account_name: f.bank_account_name || '', bank_account_number: f.bank_account_number || '',
        bank_ifsc: f.bank_ifsc || '', bank_name: f.bank_name || '', instructions: f.instructions || '',
      }
      // Secrets are only sent when typed (or explicitly removed), never echoed.
      if (secret !== KEEP) body.razorpay_key_secret = secret === '\u0000' ? '' : secret
      if (hook !== KEEP) body.razorpay_webhook_secret = hook === '\u0000' ? '' : hook
      const saved = await paymentSettingsApi.update(body)
      setF({ ...saved }); setSecret(KEEP); setHook(KEEP)
      success('Payment settings saved', 'Residents see the options on their rent screen.')
    } catch (err) { error('Could not save', err.message) }
    finally { setBusy(false) }
  }

  const test = async () => {
    setTesting(true)
    try {
      const r = await paymentSettingsApi.testRazorpay()
      success('Razorpay accepted the keys', `These are ${r.mode} keys.`)
    } catch (err) { error('Razorpay check failed', err.message) }
    finally { setTesting(false) }
  }

  const pickImage = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    try { setF((x) => ({ ...x, qr_image: '' })); const data = await shrinkImage(file); setF((x) => ({ ...x, qr_image: data })) }
    catch { error('That picture could not be read.') }
  }

  const copy = async (text) => { try { await navigator.clipboard.writeText(text); success('Copied') } catch { /* */ } }

  return (
    <div className="space-y-4 max-w-3xl">
      <InlineAlert tone="info" title="Residents see a Pay now button on every unpaid invoice">
        Switch on any of the options below. UPI and bank transfers need the resident to enter
        the transaction number (UTR); they stay pending until you verify them under Payments.
        Razorpay payments confirm themselves.
      </InlineAlert>

      <Card>
        <CardHeader title="Online payments with Razorpay"
          subtitle="Card, UPI and net banking inside the app. Money goes straight to your Razorpay account."
          action={f.mode && <StatusBadge status={f.mode === 'test' ? 'Test keys' : 'Live keys'}
            tone={f.mode === 'test' ? 'amber' : 'emerald'} />} />
        <div className="p-5 space-y-4">
          <div className="rounded-lg border border-line px-3">
            <Toggle checked={!!f.razorpay_enabled} disabled={!manage} onChange={set('razorpay_enabled')}
              label="Let residents pay online" ariaLabel="Let residents pay online"
              description={f.online_ready ? 'Ready - residents see "Pay online".' : 'Add your keys below first.'} />
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <FormField label="Key id" hint="Starts with rzp_live_ or rzp_test_.">
              <Input value={f.razorpay_key_id || ''} disabled={!manage} onChange={set('razorpay_key_id')}
                placeholder="rzp_live_XXXXXXXXXXXX" className="font-mono" autoComplete="off" />
            </FormField>
            <FormField label="Key secret" hint={f.has_key_secret
              ? (f.key_secret_readable ? 'Saved. Type a new one to replace it.' : 'Saved but unreadable - enter it again.')
              : 'Shown once in Razorpay when you generate the key.'}>
              <div className="flex gap-2">
                <Input type="password" autoComplete="new-password" disabled={!manage}
                  value={secret === '\u0000' ? '' : secret}
                  placeholder={f.has_key_secret ? '•••••••• saved' : 'Paste the key secret'}
                  onChange={(e) => setSecret(e.target.value)} />
                {f.has_key_secret && manage && (
                  <Button icon={Trash2} aria-label="Remove key secret" onClick={() => setSecret('\u0000')}
                    className={secret === '\u0000' ? 'text-rose-600' : ''} />
                )}
              </div>
            </FormField>
          </div>
          <details className="rounded-lg border border-line p-3">
            <summary className="text-sm font-medium text-slate-800 cursor-pointer">
              Webhook (recommended) {f.has_webhook_secret && <span className="text-emerald-700 font-normal">· set</span>}
            </summary>
            <p className="text-xs text-slate-500 mt-2">
              If a resident's phone dies mid-payment, Razorpay still tells PGuru through this
              address. In Razorpay: Settings, Webhooks, add this URL with the events
              payment.captured and payment.failed, and paste the same secret here.
            </p>
            <div className="mt-3 flex items-center gap-2">
              <code className="flex-1 min-w-0 truncate text-xs bg-slate-50 border border-line rounded-md px-2.5 py-2">{webhookUrl}</code>
              <Button size="sm" icon={Copy} onClick={() => copy(webhookUrl)}>Copy</Button>
            </div>
            <FormField label="Webhook secret" className="mt-3">
              <Input type="password" autoComplete="new-password" disabled={!manage}
                value={hook === '\u0000' ? '' : hook}
                placeholder={f.has_webhook_secret ? '•••••••• saved' : 'Choose a secret and paste it in both places'}
                onChange={(e) => setHook(e.target.value)} />
            </FormField>
          </details>
          {manage && (
            <Button icon={PlugZap} loading={testing} disabled={!f.has_key_secret || !f.razorpay_key_id}
              onClick={test}>Check the keys work</Button>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader title="UPI" subtitle="No Razorpay needed. Residents pay from any UPI app and enter the UTR." />
        <div className="p-5 space-y-4">
          <div className="rounded-lg border border-line px-3">
            <Toggle checked={!!f.upi_enabled} disabled={!manage} onChange={set('upi_enabled')}
              label="Accept UPI" ariaLabel="Accept UPI"
              description="The app draws a UPI QR with the amount and invoice number filled in." />
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <FormField label="UPI id" hint="Like sunrisepg@okhdfcbank.">
              <Input value={f.upi_id || ''} disabled={!manage} onChange={set('upi_id')} autoComplete="off" />
            </FormField>
            <FormField label="Name shown to the payer">
              <Input value={f.upi_payee_name || ''} disabled={!manage} onChange={set('upi_payee_name')} />
            </FormField>
          </div>
          <div>
            <p className="text-[13px] font-medium text-slate-700 mb-1.5">Your printed QR (optional)</p>
            <div className="flex items-center gap-3">
              {f.qr_image ? (
                <img src={f.qr_image} alt="Your UPI QR" className="h-24 w-24 object-contain rounded-lg border border-line bg-white" />
              ) : (
                <span className="h-24 w-24 rounded-lg border border-dashed border-line inline-flex items-center justify-center text-slate-300">
                  <Smartphone size={26} /></span>
              )}
              {manage && (
                <div className="flex flex-col gap-2">
                  <label className="inline-flex">
                    <input type="file" accept="image/*" className="sr-only" onChange={pickImage} />
                    <span className="h-9 px-3 inline-flex items-center gap-2 rounded-lg border border-line text-sm text-slate-700 bg-white hover:bg-slate-50 cursor-pointer">
                      <ImagePlus size={15} />{f.qr_image ? 'Replace photo' : 'Add a photo'}</span>
                  </label>
                  {f.qr_image && <button onClick={() => setF((x) => ({ ...x, qr_image: '' }))}
                    className="text-xs text-rose-600 hover:underline text-left">Remove</button>}
                </div>
              )}
            </div>
            <p className="text-2xs text-slate-500 mt-1.5">Not needed if you entered your UPI id - that QR
              is drawn for you with the amount filled in.</p>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader title="Bank transfer" subtitle="NEFT, IMPS or RTGS. Residents enter the bank's reference number." />
        <div className="p-5 space-y-4">
          <div className="rounded-lg border border-line px-3">
            <Toggle checked={!!f.bank_enabled} disabled={!manage} onChange={set('bank_enabled')}
              label="Accept bank transfers" ariaLabel="Accept bank transfers" />
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <FormField label="Account holder name">
              <Input value={f.bank_account_name || ''} disabled={!manage} onChange={set('bank_account_name')} />
            </FormField>
            <FormField label="Account number">
              <Input value={f.bank_account_number || ''} disabled={!manage} inputMode="numeric"
                onChange={set('bank_account_number')} className="tnum" />
            </FormField>
            <FormField label="IFSC">
              <Input value={f.bank_ifsc || ''} disabled={!manage} onChange={set('bank_ifsc')}
                className="uppercase font-mono" maxLength={11} />
            </FormField>
            <FormField label="Bank and branch">
              <Input value={f.bank_name || ''} disabled={!manage} onChange={set('bank_name')} />
            </FormField>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader title="Note for residents" subtitle="Shown under the payment options." />
        <div className="p-5">
          <Textarea rows={2} maxLength={500} value={f.instructions || ''} disabled={!manage}
            onChange={set('instructions')} placeholder="Please pay by the 5th. Cash is accepted at the desk 9 am – 7 pm." />
        </div>
      </Card>

      {manage && (
        <div className="flex justify-end">
          <Button variant="primary" icon={Save} loading={busy} onClick={save}>Save payment settings</Button>
        </div>
      )}
    </div>
  )
}
