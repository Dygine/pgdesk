import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CreditCard, TrendingUp, RefreshCw, Pencil } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, DataTable, StatusBadge, StatCard, EmptyState,
  Modal, FormField, Input, Textarea, Skeleton, InlineAlert,
} from '@/components/ui'
import { inr, num, dateFmt } from '@/lib/format'

const LIMIT_KEYS = ['branches', 'buildings', 'floors', 'rooms', 'beds',
  'customers', 'users', 'admins', 'storage_gb', 'monthly_transactions']

export default function Subscriptions() {
  const { success, error } = useToast()
  const plans = useApi(() => subscriptionApi.plans(), [])
  const subs = useApi(() => subscriptionApi.list(), [])
  const [editing, setEditing] = useState(null)

  const rows = subs.data || []
  const mrr = rows
    .filter((s) => ['ACTIVE', 'EXPIRING'].includes(s.organization_status))
    .reduce((a, s) => a + s.price, 0)

  const sweep = async () => {
    try {
      const r = await subscriptionApi.sweep()
      success('Expiry statuses recomputed', `${r.organizations_updated} updated.`)
      subs.reload()
    } catch (err) { error('Sweep failed', err.message) }
  }

  return (
    <>
      <PageHeader title="Subscriptions"
        subtitle="Plans, their limits, and where every tenant sits."
        actions={<Button icon={RefreshCw} onClick={sweep}>Recompute expiry</Button>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Estimated MRR" value={inr(mrr)} icon={TrendingUp} tone="emerald"
          sub="active plans, at list price" />
        <StatCard label="Subscriptions" value={num(rows.length)} icon={CreditCard} tone="brand" />
        <StatCard label="Expiring in 30 days"
          value={num(rows.filter((s) => s.days_remaining >= 0 && s.days_remaining <= 30).length)}
          tone="amber" />
        <StatCard label="Lapsed"
          value={num(rows.filter((s) => s.days_remaining < 0).length)} tone="rose" />
      </div>

      <Card className="mb-4">
        <CardHeader title="Plans" subtitle="Limits are stored in the database and enforced by the API" />
        {plans.loading ? <div className="p-4"><Skeleton className="h-32" /></div> : (
          <div className="p-4 grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {(plans.data || []).map((p) => (
              <div key={p.id} className="rounded-lg border border-line p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">{p.name}</p>
                    <p className="text-lg font-semibold text-slate-900 tnum">
                      {inr(p.price)}<span className="text-xs font-normal text-slate-500">/mo</span>
                    </p>
                  </div>
                  <Button size="sm" icon={Pencil} onClick={() => setEditing(p)}>Edit</Button>
                </div>
                <dl className="mt-3 space-y-1">
                  {LIMIT_KEYS.slice(0, 6).map((k) => (
                    <div key={k} className="flex justify-between text-2xs">
                      <dt className="text-slate-500 capitalize">{k.replace('_', ' ')}</dt>
                      <dd className="tnum text-slate-700">{p.limits[k]}</dd>
                    </div>
                  ))}
                </dl>
                <div className="mt-3 flex items-center gap-1.5">
                  <StatusBadge status={p.status} dot />
                  <span className="text-2xs text-slate-500">
                    {rows.filter((s) => s.plan_code === p.code).length} tenants
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="Tenant subscriptions" subtitle="Sorted by expiry" />
        {subs.error ? (
          <InlineAlert tone="error" className="m-4">{subs.error.message}</InlineAlert>
        ) : (
          <DataTable rows={rows} pageSize={15}
            columns={[
              { key: 'organization', header: 'Organisation',
                render: (s) => (
                  <Link to={`/master/organizations/${s.organization_id}`}
                    className="min-w-0 block hover:text-brand-800">
                    <p className="font-medium text-slate-900 truncate">{s.organization}</p>
                    <p className="text-xs text-slate-500">{s.city || '—'}</p>
                  </Link>
                ) },
              { key: 'plan', header: 'Plan',
                render: (s) => <div><p className="text-sm text-slate-800">{s.plan}</p>
                  <p className="text-2xs text-slate-500 tnum">{inr(s.price)}/mo</p></div> },
              { key: 'end_date', header: 'Expires',
                render: (s) => <span className="tnum text-sm text-slate-700">{dateFmt(s.end_date)}</span> },
              { key: 'days_remaining', header: 'Remaining', align: 'right',
                render: (s) => <span className={`tnum text-sm ${
                  s.days_remaining < 0 ? 'text-rose-600'
                    : s.days_remaining <= 30 ? 'text-amber-600' : 'text-slate-700'}`}>
                  {s.days_remaining < 0 ? `${Math.abs(s.days_remaining)}d ago` : `${s.days_remaining}d`}
                </span> },
              { key: 'organization_status', header: 'Org',
                render: (s) => <StatusBadge status={s.organization_status} dot /> },
              { key: 'status', header: 'Subscription',
                render: (s) => <StatusBadge status={s.status} /> },
            ]}
            mobileCard={(s) => (
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">{s.organization}</p>
                    <p className="text-xs text-slate-500">{s.plan} · {inr(s.price)}/mo</p>
                  </div>
                  <StatusBadge status={s.organization_status} />
                </div>
                <p className="text-xs text-slate-500 tnum">
                  Expires {dateFmt(s.end_date)} · {s.days_remaining}d
                </p>
              </div>
            )}
            empty={<EmptyState icon={CreditCard} title="No subscriptions yet" />} />
        )}
      </Card>

      <EditPlanModal plan={editing} onClose={() => setEditing(null)}
        onDone={() => { setEditing(null); plans.reload() }} />
    </>
  )
}

function EditPlanModal({ plan, onClose, onDone }) {
  const { success, error } = useToast()
  const [f, setF] = useState(null)
  const [busy, setBusy] = useState(false)

  if (plan && !f) {
    setF({ name: plan.name, price: String(plan.price), support_level: plan.support_level || '',
      features: (plan.features || []).join('\n'),
      limits: Object.fromEntries(LIMIT_KEYS.map((k) => [k, String(plan.limits[k] ?? 0)])) })
  }
  if (!plan || !f) return null

  const close = () => { setF(null); onClose() }

  const submit = async () => {
    setBusy(true)
    try {
      await subscriptionApi.updatePlan(plan.id, {
        name: f.name, price: Number(f.price), support_level: f.support_level,
        features: f.features.split('\n').map((s) => s.trim()).filter(Boolean),
        limits: Object.fromEntries(Object.entries(f.limits).map(([k, v]) => [k, Number(v)])),
      })
      success(`${f.name} updated`)
      setF(null)
      onDone()
    } catch (err) { error('Could not update the plan', err.message) } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={close} size="md" title={`Edit ${plan.name}`}
      subtitle="Limits apply to every tenant on this plan that has no override."
      footer={<><Button onClick={close}>Cancel</Button>
        <Button variant="primary" loading={busy} onClick={submit}>Save plan</Button></>}>
      <div className="space-y-5">
        <div className="grid sm:grid-cols-2 gap-4">
          <FormField label="Name" required>
            <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </FormField>
          <FormField label="Monthly price">
            <Input inputMode="numeric" className="tnum" value={f.price}
              onChange={(e) => setF({ ...f, price: e.target.value })} />
          </FormField>
          <FormField label="Support level" className="sm:col-span-2">
            <Input value={f.support_level}
              onChange={(e) => setF({ ...f, support_level: e.target.value })} />
          </FormField>
        </div>

        <div>
          <p className="text-[13px] font-semibold text-slate-800 mb-3 pb-2 border-b border-line">
            Limits
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            {LIMIT_KEYS.map((k) => (
              <FormField key={k} label={k.replace('_', ' ')}>
                <Input inputMode="numeric" className="tnum" value={f.limits[k]}
                  onChange={(e) => setF({ ...f, limits: { ...f.limits, [k]: e.target.value } })} />
              </FormField>
            ))}
          </div>
        </div>

        <FormField label="Features" hint="One per line.">
          <Textarea rows={4} value={f.features}
            onChange={(e) => setF({ ...f, features: e.target.value })} />
        </FormField>
      </div>
    </Modal>
  )
}
