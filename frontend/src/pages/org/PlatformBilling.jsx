import { useState } from 'react'
import {
  Wallet, CreditCard, Ticket, RefreshCw, CheckCircle2, AlertTriangle,
  ExternalLink, Zap, Receipt,
} from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { platformBillingApi } from '@/services/api/platformBillingApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, EmptyState, StatCard, Modal,
  FormField, Input, InlineAlert, Skeleton, IconButton,
} from '@/components/ui'
import { inr, dateFmt } from '@/lib/format'

/**
 * What this PG pays PGuru.
 *
 * Deliberately not the same screen as Invoices or Payments, which are residents
 * paying this PG. Putting the two on one page would invite exactly the
 * confusion the whole architecture exists to avoid - one is money coming in
 * through the owner's own gateway, this is money going out to the platform.
 */
export default function PlatformBilling() {
  const { success, error } = useToast()
  const [topupOpen, setTopupOpen] = useState(false)
  const [amount, setAmount] = useState('')
  const [coupon, setCoupon] = useState('')
  const [applied, setApplied] = useState(null)
  const [busy, setBusy] = useState(false)

  const summary = useApi(() => platformBillingApi.summary(), [])
  const history = useApi(() => platformBillingApi.history(25), [])

  const s = summary.data
  const wallet = s?.wallet
  const sub = s?.subscription
  const due = s?.due

  const reload = () => { summary.refetch?.(); history.refetch?.() }

  async function applyCoupon() {
    if (!coupon.trim()) return
    setBusy(true)
    try {
      const quote = await platformBillingApi.previewCoupon(coupon.trim())
      setApplied(quote)
      success(`Coupon applied — you save ${inr(quote.discount_paise / 100)}`)
    } catch (e) {
      setApplied(null)
      error(e.message || 'That coupon could not be applied')
    } finally {
      setBusy(false)
    }
  }

  /**
   * Both payment routes send the owner somewhere or settle immediately, so the
   * button stays disabled until we know which happened. A double-submitted
   * renewal is guarded server-side by the idempotency key, but the UI should
   * not invite it.
   */
  async function payByCard() {
    setBusy(true)
    try {
      const res = await platformBillingApi.subscriptionCheckout({
        coupon_code: applied ? coupon.trim() : null,
        success_url: window.location.href,
        cancel_url: window.location.href,
      })
      if (res.checkout_url) window.location.href = res.checkout_url
    } catch (e) {
      error(e.message || 'Could not start the payment')
      setBusy(false)
    }
  }

  async function payByWallet() {
    setBusy(true)
    try {
      const res = await platformBillingApi.payFromWallet({
        coupon_code: applied ? coupon.trim() : null,
      })
      success(`Paid. Your subscription runs to ${dateFmt(res.current_period_end)}.`)
      setCoupon(''); setApplied(null)
      reload()
    } catch (e) {
      // 409 is a normal outcome, not a fault: the balance is short.
      error(e.message || 'Could not pay from the wallet')
    } finally {
      setBusy(false)
    }
  }

  async function startTopup() {
    setBusy(true)
    try {
      const res = await platformBillingApi.topup(Number(amount))
      if (res.checkout_url) window.location.href = res.checkout_url
    } catch (e) {
      error(e.message || 'Could not start the top-up')
      setBusy(false)
    }
  }

  async function toggleAutoDebit() {
    try {
      await platformBillingApi.setAutoDebit(!s.auto_debit_enabled)
      success(s.auto_debit_enabled
        ? 'Automatic renewal turned off'
        : 'Automatic renewal turned on')
      reload()
    } catch (e) {
      error(e.message || 'Could not change that setting')
    }
  }

  if (summary.loading) return <Skeleton rows={6} />

  const net = applied ? applied.net_paise : due?.net_paise
  const walletCovers = wallet && net != null && wallet.balance_paise >= net

  return (
    <PermissionGuard permission="org.settings.manage">
      <PageHeader
        title="Subscription & wallet"
        subtitle="What you pay for PGuru. Separate from the rent your residents pay you."
        actions={
          <Button variant="ghost" onClick={reload} icon={RefreshCw}>Refresh</Button>
        }
      />

      {!s?.gateway_available && (
        <InlineAlert variant="warning" className="mb-4">
          Online payment is not set up on this platform yet. Contact support to
          renew your subscription.
        </InlineAlert>
      )}

      {/*
        A cached balance must never be presented as current. Someone who
        believes they have money they do not is about to have a renewal fail.
      */}
      {wallet && !wallet.live && (
        <InlineAlert variant="warning" className="mb-4">
          Showing your last known balance
          {wallet.as_of ? ` from ${dateFmt(wallet.as_of)}` : ''} — the payments
          service could not be reached just now.
        </InlineAlert>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-6">
        <StatCard
          label="Wallet balance"
          value={inr(wallet?.balance_rupees ?? 0)}
          icon={Wallet}
          hint={wallet?.live ? 'up to date' : 'last known'}
        />
        <StatCard
          label="Current plan"
          value={sub?.plan_name || '—'}
          icon={CreditCard}
          hint={sub ? `${inr(sub.price_rupees)} / ${sub.billing_cycle.toLowerCase()}` : ''}
        />
        <StatCard
          label="Renews"
          value={sub ? dateFmt(sub.current_period_end) : '—'}
          icon={Receipt}
          hint={sub ? `${sub.days_remaining} day${sub.days_remaining === 1 ? '' : 's'} left` : ''}
        />
        <StatCard
          label="Next charge"
          value={net != null ? inr(net / 100) : '—'}
          icon={Zap}
          hint={walletCovers ? 'covered by wallet' : 'top up or pay by card'}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Pay your subscription">
          {!sub ? (
            <EmptyState title="No plan yet"
              description="Contact support to choose a subscription plan." />
          ) : (
            <>
              <div className="space-y-2 text-sm">
                <Row label={sub.plan_name} value={inr(due?.gross_paise / 100 || 0)} />
                {applied?.discount_paise > 0 && (
                  <Row
                    label={`Coupon ${applied.coupon_code}`}
                    value={`− ${inr(applied.discount_paise / 100)}`}
                    tone="positive"
                  />
                )}
                <div className="border-t pt-2 mt-2">
                  <Row label="Total" value={inr((net ?? 0) / 100)} strong />
                </div>
              </div>

              <div className="mt-4 flex gap-2 items-end">
                <FormField label="Coupon code" className="flex-1">
                  <Input
                    value={coupon}
                    onChange={(e) => { setCoupon(e.target.value); setApplied(null) }}
                    placeholder="SAVE20"
                  />
                </FormField>
                <Button variant="secondary" onClick={applyCoupon}
                  disabled={busy || !coupon.trim()} icon={Ticket}>
                  Apply
                </Button>
              </div>

              {s?.available_coupons?.length > 0 && (
                <div className="mt-3 text-xs text-muted">
                  Available to you:{' '}
                  {s.available_coupons.map((c) => (
                    <button
                      key={c.code}
                      type="button"
                      className="underline mr-2"
                      onClick={() => { setCoupon(c.code); setApplied(null) }}
                    >
                      {c.code}
                    </button>
                  ))}
                </div>
              )}

              <div className="mt-5 flex flex-wrap gap-2">
                <Button
                  onClick={payByWallet}
                  disabled={busy || !walletCovers || !s?.gateway_available}
                  icon={Wallet}
                >
                  Pay from wallet
                </Button>
                <Button
                  variant="secondary"
                  onClick={payByCard}
                  disabled={busy || !s?.gateway_available}
                  icon={CreditCard}
                >
                  Pay by card or UPI
                </Button>
              </div>

              {!walletCovers && wallet && (
                <p className="mt-3 text-xs text-muted">
                  Your wallet is {inr(Math.max(0, (net ?? 0) - wallet.balance_paise) / 100)}{' '}
                  short of this charge.
                </p>
              )}
            </>
          )}
        </Card>

        <Card title="Wallet">
          <p className="text-sm text-muted mb-4">
            Prepaid balance for PGuru subscriptions. It can only be spent here —
            it cannot be withdrawn as cash or transferred to anyone else.
          </p>

          <Button onClick={() => setTopupOpen(true)}
            disabled={!s?.gateway_available} icon={Wallet}>
            Top up
          </Button>

          <div className="mt-5 pt-4 border-t">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={!!s?.auto_debit_enabled}
                onChange={toggleAutoDebit}
                className="mt-1"
              />
              <span className="text-sm">
                <span className="font-medium">Renew automatically from my wallet</span>
                <span className="block text-muted text-xs mt-0.5">
                  On renewal day we take the charge from your balance, so your
                  service never lapses because nobody pressed a button. You are
                  warned in advance if the balance will not cover it.
                </span>
              </span>
            </label>
          </div>
        </Card>
      </div>

      <Card title="History" className="mt-4">
        {history.loading ? <Skeleton rows={3} /> : (
          <DataTable
            columns={[
              { key: 'created_at', label: 'Date',
                render: (r) => dateFmt(r.created_at) },
              { key: 'purpose', label: 'For',
                render: (r) => r.purpose === 'wallet_topup'
                  ? 'Wallet top-up'
                  : `Subscription${r.period ? ` — ${dateFmt(r.period)}` : ''}` },
              { key: 'method', label: 'Paid by',
                render: (r) => r.method === 'wallet' ? 'Wallet' : 'Card / UPI' },
              { key: 'discount_rupees', label: 'Discount', align: 'right',
                render: (r) => r.discount_rupees > 0
                  ? `− ${inr(r.discount_rupees)}` : '—' },
              { key: 'net_rupees', label: 'Amount', align: 'right',
                render: (r) => inr(r.net_rupees) },
              { key: 'status', label: 'Status',
                render: (r) => <StatusBadge status={r.status} /> },
              { key: 'invoice', label: '', align: 'right',
                render: (r) => r.invoice_url ? (
                  <a href={r.invoice_url} target="_blank" rel="noreferrer"
                     className="inline-flex items-center gap-1 text-xs underline">
                    {r.invoice_number} <ExternalLink size={12} />
                  </a>
                ) : null },
            ]}
            rows={history.data?.data || []}
            empty={<EmptyState title="Nothing yet"
              description="Your subscription payments will appear here." />}
          />
        )}
      </Card>

      <Modal open={topupOpen} onClose={() => setTopupOpen(false)} title="Top up wallet">
        <FormField label="Amount (₹)">
          <Input type="number" min="100" value={amount}
            onChange={(e) => setAmount(e.target.value)} placeholder="5000" />
        </FormField>
        <div className="flex gap-2 mt-3 flex-wrap">
          {[1000, 5000, 10000, 25000].map((v) => (
            <Button key={v} variant="ghost" size="sm"
              onClick={() => setAmount(String(v))}>
              {inr(v)}
            </Button>
          ))}
        </div>
        <div className="mt-5 flex gap-2 justify-end">
          <Button variant="ghost" onClick={() => setTopupOpen(false)}>Cancel</Button>
          <Button onClick={startTopup} disabled={busy || Number(amount) < 100}>
            Continue to payment
          </Button>
        </div>
      </Modal>
    </PermissionGuard>
  )
}

function Row({ label, value, strong, tone }) {
  return (
    <div className="flex justify-between">
      <span className={strong ? 'font-medium' : 'text-muted'}>{label}</span>
      <span className={[
        'tabular-nums',
        strong ? 'font-semibold' : '',
        tone === 'positive' ? 'text-emerald-600' : '',
      ].join(' ')}>{value}</span>
    </div>
  )
}
