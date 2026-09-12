import { useEffect, useState } from 'react'
import {
  IndianRupee, Receipt, Wallet, CreditCard, Smartphone, Landmark, Copy, ExternalLink,
  ShieldCheck, Clock3,
} from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { meApi } from '@/services/api/meApi'
import { useToast } from '@/context/ToastContext'
import { openCheckout, upiLink } from '@/lib/razorpay'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, StatCard, StatusBadge, EmptyState, Skeleton, InlineAlert, Button,
  Modal, FormField, Input, QrCode,
} from '@/components/ui'
import { inr, dateFmt, today } from '@/lib/format'

const cx = (...a) => a.filter(Boolean).join(' ')
const SOURCE = { razorpay: 'Paid online', resident: 'You reported it', desk: 'At the desk' }

function CopyRow({ label, value }) {
  const { success } = useToast()
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); success(`${label} copied`) } catch { /* no clipboard */ }
  }
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <div className="min-w-0">
        <p className="text-2xs text-slate-500">{label}</p>
        <p className="text-sm font-medium text-slate-900 tnum break-all">{value}</p>
      </div>
      <button onClick={copy} aria-label={`Copy ${label}`}
        className="h-8 w-8 shrink-0 inline-flex items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100">
        <Copy size={15} />
      </button>
    </div>
  )
}

/**
 * Paying one invoice. Online payments are recorded only after the server has
 * checked Razorpay's signature. UPI and bank transfers happen outside the app,
 * so the resident types the transaction number (UTR) - required - and the
 * payment waits for the office to match it against the bank statement.
 */
function PayModal({ invoice, options, onClose, onPaid }) {
  const { success, error } = useToast()
  const due = Math.max(0, Number(invoice.balance) - Number(invoice.pending_amount || 0))
  const methods = [
    options.online && ['online', 'Pay online', CreditCard],
    options.upi && ['upi', 'UPI', Smartphone],
    options.bank && ['bank', 'Bank transfer', Landmark],
  ].filter(Boolean)
  const [method, setMethod] = useState(methods[0]?.[0])
  const [amount, setAmount] = useState(String(due))
  const [utr, setUtr] = useState('')
  const [paidOn, setPaidOn] = useState(today())
  const [busy, setBusy] = useState(false)

  const value = Number(amount) || 0
  const valid = value > 0 && value <= due + 0.009
  const cleanUtr = utr.replace(/\s+/g, '')
  const utrOk = method === 'upi' ? /^\d{12}$/.test(cleanUtr) : /^[A-Za-z0-9]{6,22}$/.test(cleanUtr)

  const payOnline = async () => {
    if (!valid) return error(`Enter an amount up to ${inr(due, { paise: true })}.`)
    setBusy(true)
    try {
      const order = await meApi.startOnlinePayment({ invoice_id: invoice.id, amount: value })
      const res = await openCheckout(order)
      const confirmed = await meApi.confirmOnlinePayment(res)
      success('Payment received', `${confirmed.payment_number} · thank you.`)
      onPaid()
    } catch (err) {
      if (err.dismissed) return
      error('Payment not completed', err.message)
    } finally { setBusy(false) }
  }

  const report = async () => {
    if (!valid) return error(`Enter an amount up to ${inr(due, { paise: true })}.`)
    if (!cleanUtr) return error('Enter the transaction number (UTR). It is required.')
    if (!utrOk) {
      return error(method === 'upi'
        ? 'A UPI transaction number is 12 digits. Find it in your UPI app under payment details.'
        : 'Enter the bank reference exactly as shown: 6 to 22 letters or digits.')
    }
    setBusy(true)
    try {
      await meApi.submitPayment({ invoice_id: invoice.id, amount: value,
        method: method === 'upi' ? 'UPI' : 'BANK_TRANSFER', utr: cleanUtr, paid_on: paidOn })
      success('Sent for confirmation', 'It shows as pending until the office checks it.')
      onPaid()
    } catch (err) { error('Could not send that', err.message) }
    finally { setBusy(false) }
  }

  const link = options.upi && upiLink({ upiId: options.upi.upi_id, payee: options.upi.payee_name,
    amount: value || undefined, note: invoice.invoice_number })

  return (
    <Modal open onClose={onClose} size="md" title={`Pay ${invoice.invoice_number}`}
      subtitle={`${inr(due, { paise: true })} left to pay${Number(invoice.pending_amount) > 0 ? `, ${inr(invoice.pending_amount)} already waiting for confirmation` : ''}`}
      footer={method === 'online'
        ? <><Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" icon={ShieldCheck} loading={busy} disabled={!valid} onClick={payOnline}>
            Pay {inr(value, { paise: true })}</Button></>
        : <><Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} disabled={!valid || !cleanUtr} onClick={report}>
            I have paid - send for confirmation</Button></>}>
      <div className="space-y-4">
        {methods.length > 1 && (
          <div role="tablist" className="grid gap-1.5 p-1 rounded-xl bg-slate-100"
            style={{ gridTemplateColumns: `repeat(${methods.length}, minmax(0, 1fr))` }}>
            {methods.map(([key, text, Icon]) => (
              <button key={key} role="tab" aria-selected={method === key} onClick={() => setMethod(key)}
                className={cx('h-9 rounded-lg text-sm inline-flex items-center justify-center gap-1.5 transition-colors',
                  method === key ? 'bg-white shadow-sm text-slate-900 font-medium' : 'text-slate-600')}>
                <Icon size={15} />{text}
              </button>
            ))}
          </div>
        )}

        <FormField label="Amount" hint="Pay in full, or part of it.">
          <Input inputMode="decimal" className="tnum" value={amount}
            onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))} />
        </FormField>

        {method === 'online' && (
          <InlineAlert tone="info" icon={ShieldCheck} title="Card, UPI or net banking through Razorpay">
            The payment is confirmed automatically - no transaction number needed. The money goes
            straight to the PG.
          </InlineAlert>
        )}

        {method === 'upi' && (
          <>
            <div className="rounded-xl border border-line p-4 flex flex-col sm:flex-row gap-4 items-center">
              <QrCode value={link} size={176} alt="UPI payment QR" />
              <div className="flex-1 min-w-0 w-full">
                <p className="text-sm text-slate-700">Scan with any UPI app. The amount and invoice
                  number are filled in for you.</p>
                <CopyRow label="UPI id" value={options.upi.upi_id} />
                <a href={link}
                  className="mt-1 h-10 w-full inline-flex items-center justify-center gap-2 rounded-lg bg-brand-50 text-brand-800 text-sm font-medium hover:bg-brand-100">
                  <ExternalLink size={15} /> Open a UPI app on this phone</a>
              </div>
            </div>
            {options.upi.qr_image && (
              <details className="rounded-lg border border-line p-3">
                <summary className="text-sm text-slate-700 cursor-pointer">Or use the PG's own QR code</summary>
                <img src={options.upi.qr_image} alt="The PG's UPI QR code" className="mt-3 mx-auto max-h-64 rounded" />
                <p className="text-2xs text-slate-500 mt-2 text-center">Type the amount yourself when using this one.</p>
              </details>
            )}
          </>
        )}

        {method === 'bank' && (
          <div className="rounded-xl border border-line px-4 py-2 divide-y divide-line">
            <CopyRow label="Account name" value={options.bank.account_name} />
            <CopyRow label="Account number" value={options.bank.account_number} />
            <CopyRow label="IFSC" value={options.bank.ifsc} />
            {options.bank.bank_name && <CopyRow label="Bank" value={options.bank.bank_name} />}
          </div>
        )}

        {method !== 'online' && (
          <div className="grid grid-cols-[1fr_auto] gap-3">
            <FormField label="Transaction number (UTR)" required
              error={cleanUtr && !utrOk ? (method === 'upi' ? '12 digits, from your UPI app.' : '6 to 22 letters or digits.') : undefined}
              hint={method === 'upi' ? 'The 12-digit UPI reference in your app\u2019s payment details.' : 'The reference your bank shows for the transfer.'}>
              <Input value={utr} onChange={(e) => setUtr(e.target.value)} className="tnum font-mono"
                inputMode={method === 'upi' ? 'numeric' : 'text'} maxLength={30}
                placeholder={method === 'upi' ? '412345678901' : 'HDFCR52026091012345'} />
            </FormField>
            <FormField label="Paid on">
              <Input type="date" max={today()} value={paidOn} onChange={(e) => setPaidOn(e.target.value)} className="w-40" />
            </FormField>
          </div>
        )}

        {options.instructions && <p className="text-xs text-slate-500 whitespace-pre-line">{options.instructions}</p>}
      </div>
    </Modal>
  )
}

export default function MyRent() {
  const { data, loading, error, reload } = useApi(() => meApi.rent(), [])
  const options = useApi(() => meApi.paymentOptions(), [])
  const [paying, setPaying] = useState(null)
  const opts = options.data

  useEffect(() => {
    const onResume = () => reload()
    window.addEventListener('pgguru:resume', onResume)
    return () => window.removeEventListener('pgguru:resume', onResume)
  }, [reload])

  if (error) {
    return (<><PageHeader title="My rent" />
      <InlineAlert tone="error" title="Could not load">{error.message}</InlineAlert></>)
  }
  if (loading && !data) {
    return (<><PageHeader title="My rent" /><Skeleton className="h-64" /></>)
  }

  const s = data.summary
  const canPayInApp = !!opts?.any

  return (
    <>
      <PageHeader title="My rent" subtitle="Everything you have been billed and paid." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Monthly rent" value={inr(s.monthly_rent)}
          icon={IndianRupee} tone="brand" sub={`Due on the ${s.rent_due_day}th`} />
        <StatCard label="Outstanding" value={inr(s.outstanding)}
          tone={s.outstanding > 0 ? 'amber' : 'emerald'} />
        <StatCard label="Paid this year" value={inr(s.paid_this_year)}
          icon={Wallet} tone="emerald" />
        <StatCard label="Deposit held" value={inr(s.security_deposit)} tone="slate" />
      </div>

      {s.outstanding > 0 && !canPayInApp && !options.loading && (
        <InlineAlert tone="warn" className="mb-4" title={`${inr(s.outstanding)} outstanding`}>
          Pay at the front desk. Your PG has not set up payments in the app yet. A payment shows
          here as pending until the office confirms it.
        </InlineAlert>
      )}

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Invoices" subtitle={`${data.invoices.length} shown`} />
          {data.invoices.length === 0 ? (
            <EmptyState icon={Receipt} compact title="No invoices yet" />
          ) : (
            <div className="divide-y divide-line max-h-[620px] overflow-y-auto">
              {data.invoices.map((i) => {
                const left = Math.max(0, Number(i.balance) - Number(i.pending_amount || 0))
                return (
                  <div key={i.id} className="px-5 py-3.5">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900">{i.invoice_number}</p>
                        <p className="text-2xs text-slate-500 tnum">Due {dateFmt(i.due_date)}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-sm font-semibold text-slate-900 tnum">{inr(i.total)}</p>
                        <StatusBadge status={i.status} />
                      </div>
                    </div>
                    <ul className="mt-2 space-y-0.5">
                      {i.items.map((it, n) => (
                        <li key={n} className="flex justify-between text-2xs text-slate-500">
                          <span className="truncate">{it.description}</span>
                          <span className="tnum shrink-0">{inr(it.amount)}</span>
                        </li>
                      ))}
                    </ul>
                    {Number(i.pending_amount) > 0 && (
                      <p className="text-xs text-slate-600 tnum mt-2 inline-flex items-center gap-1.5">
                        <Clock3 size={13} className="text-amber-600" />
                        {inr(i.pending_amount)} waiting for the office to confirm
                      </p>
                    )}
                    {left > 0.009 && i.status !== 'CANCELLED' && (
                      <div className="flex items-center justify-between gap-3 mt-2.5">
                        <p className="text-xs text-amber-700 tnum">{inr(left, { paise: left % 1 !== 0 })} to pay</p>
                        {canPayInApp && (
                          <Button size="sm" variant="primary" icon={Wallet} onClick={() => setPaying(i)}>
                            Pay now</Button>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Payments" subtitle="Pending means the office has not confirmed it yet" />
          {data.payments.length === 0 ? (
            <EmptyState icon={Wallet} compact title="No payments recorded" />
          ) : (
            <div className="divide-y divide-line max-h-[620px] overflow-y-auto">
              {data.payments.map((p) => (
                <div key={p.id} className="px-5 py-3.5 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900">{p.payment_number}</p>
                    <p className="text-2xs text-slate-500 tnum">
                      {dateFmt(p.payment_date)} · {p.method.replace('_', ' ')}
                      {p.source ? ` · ${SOURCE[p.source] || p.source}` : ''}
                    </p>
                    {p.reference && <p className="text-2xs text-slate-400 tnum font-mono truncate">Ref {p.reference}</p>}
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-semibold text-slate-900 tnum">{inr(p.amount)}</p>
                    <StatusBadge status={p.status} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {paying && opts && (
        <PayModal invoice={paying} options={opts} onClose={() => setPaying(null)}
          onPaid={() => { setPaying(null); reload() }} />
      )}
    </>
  )
}
