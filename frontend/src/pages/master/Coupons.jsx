import { useState } from 'react'
import {
  Ticket, Plus, Pause, Play, Trash2, Send, IndianRupee, TrendingUp,
  RefreshCw, ShieldCheck,
} from 'lucide-react'
import { useApi } from '@/lib/useApi'
import {
  couponApi, platformRevenueApi,
} from '@/services/api/platformBillingApi'
import { organizationApi } from '@/services/api/organizationApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, CardBody, Button, DataTable, StatusBadge, EmptyState,
  StatCard, Modal, FormField, Input, Select, InlineAlert, Skeleton,
  ConfirmDialog,
} from '@/components/ui'
import { inr, dateFmt } from '@/lib/format'

/**
 * Coupons, and what the platform actually earned.
 *
 * The create form deliberately nudges toward a capped, time-bounded coupon.
 * An uncapped percentage code with no expiry and no redemption limit is a
 * standing discount on every future renewal, which is a pricing decision
 * disguised as a promotion.
 */
export default function Coupons() {
  const { success, error } = useToast()
  const [open, setOpen] = useState(false)
  const [assigning, setAssigning] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [selected, setSelected] = useState([])
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState(blank())

  const coupons = useApi(() => couponApi.list(), [])
  const revenue = useApi(() => platformRevenueApi.revenue(90), [])
  const orgs = useApi(() => organizationApi.list({ page_size: 200 }), [])
  const plans = useApi(() => subscriptionApi.plans(), [])

  const reload = () => { coupons.refetch?.(); revenue.refetch?.() }
  const r = revenue.data

  async function create() {
    setBusy(true)
    try {
      await couponApi.create({
        code: f.code,
        description: f.description || null,
        kind: f.kind,
        value: Number(f.value),
        max_discount_rupees: f.max_discount ? Number(f.max_discount) : null,
        min_amount_rupees: Number(f.min_amount || 0),
        applies_to_plans: f.plans,
        applies_to_cycles: f.cycles === '' ? null : Number(f.cycles),
        valid_from: f.valid_from || null,
        valid_until: f.valid_until || null,
        max_redemptions: f.max_redemptions ? Number(f.max_redemptions) : null,
        max_per_org: Number(f.max_per_org || 1),
      })
      success(`Coupon ${f.code} created`)
      setOpen(false); setF(blank()); reload()
    } catch (e) {
      error(e.message || 'Could not create that coupon')
    } finally {
      setBusy(false)
    }
  }

  async function togglePause(c) {
    try {
      await couponApi.update(c.id, {
        status: c.status === 'active' ? 'paused' : 'active',
      })
      reload()
    } catch (e) { error(e.message) }
  }

  async function assign() {
    setBusy(true)
    try {
      const res = await couponApi.assign(assigning.id, selected, true)
      success(`Granted to ${res.assigned} PG${res.assigned === 1 ? '' : 's'}`)
      setAssigning(null); setSelected([]); reload()
    } catch (e) {
      error(e.message || 'Could not grant that coupon')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    try {
      await couponApi.remove(deleting.id)
      success('Coupon deleted')
      setDeleting(null); reload()
    } catch (e) {
      // A redeemed coupon cannot be deleted - it is part of the financial
      // record, and the API says so.
      error(e.message)
      setDeleting(null)
    }
  }

  async function reconcile() {
    try {
      const res = await platformRevenueApi.reconcile()
      success(`Checked ${res.checked}, settled ${res.settled}`)
      reload()
    } catch (e) { error(e.message) }
  }

  async function verify() {
    try {
      await platformRevenueApi.verifyDygine()
      success('Dygine Pay credentials work')
    } catch (e) { error(e.message || 'Could not reach Dygine Pay') }
  }

  return (
    <>
      <PageHeader
        title="Coupons & revenue"
        subtitle="Discounts you grant to PG owners, and what the platform earned."
        actions={
          <div className="flex gap-2">
            <Button variant="ghost" onClick={verify} icon={ShieldCheck}>
              Test payments
            </Button>
            <Button variant="ghost" onClick={reconcile} icon={RefreshCw}>
              Reconcile
            </Button>
            <Button onClick={() => setOpen(true)} icon={Plus}>New coupon</Button>
          </div>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5 mb-6">
        <StatCard label="Subscriptions" value={inr(r?.subscription_rupees ?? 0)}
          icon={IndianRupee} sub="last 90 days" />
        <StatCard label="Top-ups" value={inr(r?.topup_rupees ?? 0)}
          icon={TrendingUp} sub="last 90 days" />
        <StatCard label="Collected" value={inr(r?.collected_rupees ?? 0)}
          icon={IndianRupee} sub={`${r?.paying_organizations ?? 0} paying PGs`} />
        <StatCard label="Discount given" value={inr(r?.discount_given_rupees ?? 0)}
          icon={Ticket} sub="via coupons" />
        {/*
          Float is money taken but not yet consumed. A liability, not revenue:
          the owner can still spend it, and within the refund window can ask for
          it back. Showing it beside revenue stops it being mistaken for profit.
        */}
        <StatCard label="Wallet float" value={inr(r?.wallet_float_rupees ?? 0)}
          icon={IndianRupee} sub="held, not yet earned" />
      </div>

      <Card>
        <CardHeader title="Coupons" subtitle="Discounts you grant to PG owners" />
        {coupons.loading ? <Skeleton className="h-40" /> : (
          <DataTable
            columns={[
              { key: 'code', header: 'Code',
                render: (c) => (
                  <div>
                    <span className="font-mono font-medium">{c.code}</span>
                    {c.is_targeted && (
                      <span className="ml-2 text-xs text-muted">
                        · {c.assigned_to.length} PG{c.assigned_to.length === 1 ? '' : 's'}
                      </span>
                    )}
                    {c.description && (
                      <div className="text-xs text-muted">{c.description}</div>
                    )}
                  </div>
                ) },
              { key: 'value_display', header: 'Discount' },
              { key: 'cycles', header: 'Cycles', align: 'center',
                render: (c) => c.applies_to_cycles == null
                  ? <span title="Applies to every renewal — a permanent price cut">
                      every
                    </span>
                  : c.applies_to_cycles },
              { key: 'used', header: 'Used', align: 'center',
                render: (c) => (
                  <span>
                    {c.usage.confirmed}
                    {c.max_redemptions ? ` / ${c.max_redemptions}` : ''}
                    {c.usage.reserved > 0 && (
                      <span className="text-xs text-muted"> (+{c.usage.reserved} held)</span>
                    )}
                  </span>
                ) },
              { key: 'given', header: 'Given away', align: 'right',
                render: (c) => inr(c.usage.total_discount_paise / 100) },
              { key: 'valid_until', header: 'Expires',
                render: (c) => c.valid_until ? dateFmt(c.valid_until) : 'never' },
              { key: 'status', header: 'Status',
                render: (c) => <StatusBadge status={c.status} /> },
              { key: 'actions', header: '', align: 'right',
                render: (c) => (
                  <div className="flex gap-1 justify-end">
                    <Button size="sm" variant="ghost"
                      onClick={() => { setAssigning(c); setSelected(c.assigned_to) }}
                      icon={Send}>Grant</Button>
                    <Button size="sm" variant="ghost" onClick={() => togglePause(c)}
                      icon={c.status === 'active' ? Pause : Play} />
                    <Button size="sm" variant="ghost" onClick={() => setDeleting(c)}
                      icon={Trash2} />
                  </div>
                ) },
            ]}
            rows={coupons.data || []}
            empty={<EmptyState title="No coupons yet"
              message="Create one to give a PG owner a discount on their renewal." />}
          />
        )}
      </Card>

      {r?.top_organizations?.length > 0 && (
        <Card className="mt-4">
          <CardHeader title="Top paying PGs" subtitle="Last 90 days" />
          <DataTable
            columns={[
              { key: 'organization', header: 'PG' },
              { key: 'paid_rupees', header: 'Paid (90 days)', align: 'right',
                render: (o) => inr(o.paid_rupees) },
            ]}
            rows={r.top_organizations}
          />
        </Card>
      )}

      {/* ------------------------------------------------------ create --- */}
      <Modal open={open} onClose={() => setOpen(false)} title="New coupon" size="lg">
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Code" hint="Uppercased automatically">
            <Input value={f.code}
              onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })}
              placeholder="DIWALI25" />
          </FormField>
          <FormField label="Description">
            <Input value={f.description}
              onChange={(e) => setF({ ...f, description: e.target.value })}
              placeholder="Diwali offer" />
          </FormField>
          <FormField label="Type">
            <Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              <option value="percent">Percentage off</option>
              <option value="fixed">Fixed amount off</option>
            </Select>
          </FormField>
          <FormField label={f.kind === 'percent' ? 'Percent' : 'Amount (₹)'}>
            <Input type="number" value={f.value}
              onChange={(e) => setF({ ...f, value: e.target.value })}
              placeholder={f.kind === 'percent' ? '20' : '500'} />
          </FormField>
          {f.kind === 'percent' && (
            <FormField label="Maximum discount (₹)"
              hint="Strongly recommended — 20% off with no cap is an open cheque">
              <Input type="number" value={f.max_discount}
                onChange={(e) => setF({ ...f, max_discount: e.target.value })}
                placeholder="500" />
            </FormField>
          )}
          <FormField label="Minimum charge (₹)">
            <Input type="number" value={f.min_amount}
              onChange={(e) => setF({ ...f, min_amount: e.target.value })}
              placeholder="0" />
          </FormField>
          <FormField label="Billing cycles"
            hint="1 = first payment only. Blank = every renewal, forever.">
            <Input type="number" value={f.cycles}
              onChange={(e) => setF({ ...f, cycles: e.target.value })}
              placeholder="1" />
          </FormField>
          <FormField label="Uses per PG">
            <Input type="number" value={f.max_per_org}
              onChange={(e) => setF({ ...f, max_per_org: e.target.value })}
              placeholder="1" />
          </FormField>
          <FormField label="Total redemptions" hint="Blank = unlimited">
            <Input type="number" value={f.max_redemptions}
              onChange={(e) => setF({ ...f, max_redemptions: e.target.value })}
              placeholder="100" />
          </FormField>
          <FormField label="Valid from">
            <Input type="date" value={f.valid_from}
              onChange={(e) => setF({ ...f, valid_from: e.target.value })} />
          </FormField>
          <FormField label="Valid until">
            <Input type="date" value={f.valid_until}
              onChange={(e) => setF({ ...f, valid_until: e.target.value })} />
          </FormField>
        </div>

        {f.kind === 'percent' && !f.max_discount && !f.max_redemptions && (
          <InlineAlert tone="warning" className="mt-4">
            No discount cap and no redemption limit. Every PG that finds this
            code gets {f.value || '?'}% off, with nothing bounding the total.
          </InlineAlert>
        )}
        {f.cycles === '' && (
          <InlineAlert tone="warning" className="mt-3">
            With no cycle limit this discount applies to every renewal for as
            long as the PG stays subscribed. That is a price change, not a promotion.
          </InlineAlert>
        )}

        <div className="mt-5 flex gap-2 justify-end">
          <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={create} disabled={busy || !f.code || !f.value}>
            Create
          </Button>
        </div>
      </Modal>

      {/* ------------------------------------------------------ assign --- */}
      <Modal open={!!assigning} onClose={() => setAssigning(null)}
        title={`Grant ${assigning?.code || ''}`}>
        <p className="text-sm text-muted mb-3">
          Granting to specific PGs makes this a private code — only they can use
          it, and it appears on their billing screen without them being told it.
          They are notified now.
        </p>
        <div className="max-h-72 overflow-y-auto border rounded divide-y">
          {(orgs.data?.items || []).map((o) => (
            <label key={o.id}
              className="flex items-center gap-2 px-3 py-2 cursor-pointer text-sm">
              <input
                type="checkbox"
                checked={selected.includes(o.id)}
                onChange={(e) => setSelected(e.target.checked
                  ? [...selected, o.id]
                  : selected.filter((x) => x !== o.id))}
              />
              <span>{o.name}</span>
              <span className="ml-auto text-xs text-muted">{o.status}</span>
            </label>
          ))}
        </div>
        <div className="mt-4 flex gap-2 justify-end">
          <Button variant="ghost" onClick={() => setAssigning(null)}>Cancel</Button>
          <Button onClick={assign} disabled={busy || selected.length === 0}>
            Grant to {selected.length}
          </Button>
        </div>
      </Modal>

      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={remove}
        title={`Delete ${deleting?.code || ''}?`}
        message="A coupon that has already been redeemed cannot be deleted — pause it instead."
        confirmLabel="Delete"
        tone="danger"
      />
    </>
  )
}

function blank() {
  return {
    code: '', description: '', kind: 'percent', value: '',
    max_discount: '', min_amount: '0', plans: [], cycles: '1',
    valid_from: '', valid_until: '', max_redemptions: '', max_per_org: '1',
  }
}
