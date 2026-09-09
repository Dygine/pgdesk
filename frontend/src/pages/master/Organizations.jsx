import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Plus, Building, Search, MoreHorizontal, CalendarPlus, ShieldOff, ShieldCheck, ArrowUpDown,
} from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { organizationApi } from '@/services/api/organizationApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard,
  Modal, FormField, Input, Select, InlineAlert, Skeleton, ProgressBar,
} from '@/components/ui'
import { inr, num, dateFmt } from '@/lib/format'

const STATUSES = ['ACTIVE', 'TRIAL', 'EXPIRING', 'EXPIRED', 'SUSPENDED', 'INACTIVE', 'CANCELLED']

export default function Organizations() {
  const navigate = useNavigate()
  const { success, error } = useToast()

  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [plan, setPlan] = useState('all')
  const [page, setPage] = useState(1)
  const [extendFor, setExtendFor] = useState(null)
  const [planFor, setPlanFor] = useState(null)

  const plans = useApi(() => subscriptionApi.plans(), [])
  const orgs = useApi(
    () => organizationApi.list({ search, status, plan, page, page_size: 20 }),
    [search, status, plan, page],
  )

  const rows = orgs.data?.items || []
  const pagination = orgs.data?.pagination

  const totals = useMemo(() => {
    const by = {}
    rows.forEach((o) => { by[o.status] = (by[o.status] || 0) + 1 })
    return by
  }, [rows])

  const act = async (fn, okMessage) => {
    try {
      await fn()
      success(okMessage)
      orgs.reload()
    } catch (err) {
      error('That did not work', err.message)
    }
  }

  const columns = [
    {
      key: 'name', header: 'Organisation',
      render: (o) => (
        <div className="min-w-0">
          <p className="font-medium text-slate-900 truncate">{o.name}</p>
          <p className="text-xs text-slate-500 truncate">{o.city || '—'} · {o.owner_name}</p>
        </div>
      ),
    },
    {
      key: 'plan', header: 'Plan', sortable: false,
      render: (o) => o.subscription
        ? <div><p className="text-sm text-slate-800">{o.subscription.plan_name}</p>
            <p className="text-2xs text-slate-500 tnum">
              expires {dateFmt(o.subscription.end_date)}</p></div>
        : <span className="text-sm text-slate-400">No plan</span>,
    },
    {
      key: 'usage', header: 'Beds', align: 'right', sortable: false,
      render: (o) => {
        const used = o.counts?.beds ?? 0
        const limit = o.subscription?.limits?.beds ?? 0
        return (
          <div className="min-w-[96px]">
            <p className="tnum text-sm text-slate-800">{used}/{limit || '—'}</p>
            {limit ? <ProgressBar value={used} max={limit} className="mt-1"
              tone={used / limit >= 0.9 ? 'rose' : 'brand'} /> : null}
          </div>
        )
      },
    },
    {
      key: 'branches', header: 'Branches', align: 'right', sortable: false,
      render: (o) => <span className="tnum text-slate-700">
        {o.counts?.branches ?? 0}/{o.subscription?.limits?.branches ?? '—'}</span>,
    },
    {
      key: 'days', header: 'Remaining', align: 'right', sortable: false,
      render: (o) => {
        const d = o.subscription?.days_remaining
        if (d == null) return <span className="text-slate-400">—</span>
        return <span className={`tnum text-sm ${d < 0 ? 'text-rose-600' : d <= 30 ? 'text-amber-600' : 'text-slate-700'}`}>
          {d < 0 ? `${Math.abs(d)}d ago` : `${d}d`}</span>
      },
    },
    { key: 'status', header: 'Status', render: (o) => <StatusBadge status={o.status} dot /> },
    {
      key: 'actions', header: '', sortable: false, align: 'right',
      render: (o) => (
        <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          <Button size="sm" icon={CalendarPlus} onClick={() => setExtendFor(o)}>Extend</Button>
          <Button size="sm" icon={ArrowUpDown} onClick={() => setPlanFor(o)}>Plan</Button>
          {o.status === 'SUSPENDED' ? (
            <Button size="sm" variant="success" icon={ShieldCheck}
              onClick={() => act(() => organizationApi.setStatus(o.id, 'ACTIVE'),
                `${o.name} reactivated.`)}>Activate</Button>
          ) : (
            <Button size="sm" variant="danger" icon={ShieldOff}
              onClick={() => act(() => organizationApi.setStatus(o.id, 'SUSPENDED'),
                `${o.name} suspended.`)}>Suspend</Button>
          )}
        </div>
      ),
    },
  ]

  return (
    <>
      <PageHeader title="Organisations"
        subtitle="Every PG on the platform, their plan and what they are using."
        actions={<Link to="/master/organizations/new">
          <Button variant="primary" icon={Plus}>Create a PG</Button>
        </Link>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="In this view" value={num(pagination?.total ?? 0)} icon={Building} tone="brand" />
        <StatCard label="Active" value={num(totals.ACTIVE || 0)} tone="emerald" />
        <StatCard label="Trial" value={num(totals.TRIAL || 0)} tone="blue" />
        <StatCard label="Needs attention"
          value={num((totals.EXPIRED || 0) + (totals.SUSPENDED || 0) + (totals.EXPIRING || 0))}
          tone="amber" />
      </div>

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={(v) => { setSearch(v); setPage(1) }}
            searchPlaceholder="Search name, owner, email or city…"
            filters={[
              { key: 'status', label: 'Status', value: status,
                onChange: (v) => { setStatus(v); setPage(1) }, options: STATUSES },
              { key: 'plan', label: 'Plan', value: plan,
                onChange: (v) => { setPlan(v); setPage(1) },
                options: (plans.data || []).map((p) => ({ value: p.code, label: p.name })) },
            ]} />
        </div>

        {orgs.error ? (
          <InlineAlert tone="error" className="m-4">{orgs.error.message}</InlineAlert>
        ) : orgs.loading && !orgs.data ? (
          <div className="p-4 space-y-2">
            {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-14" />)}
          </div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={20}
            onRowClick={(o) => navigate(`/master/organizations/${o.id}`)}
            mobileCard={(o) => (
              <div className="space-y-2">
                <div className="flex items-start gap-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-900 truncate">{o.name}</p>
                    <p className="text-xs text-slate-500 truncate">
                      {o.subscription?.plan_name || 'No plan'} · {o.city || '—'}
                    </p>
                  </div>
                  <StatusBadge status={o.status} />
                </div>
                <div className="grid grid-cols-3 gap-2 text-center pt-1">
                  {[['Branches', `${o.counts?.branches ?? 0}/${o.subscription?.limits?.branches ?? '—'}`],
                    ['Beds', `${o.counts?.beds ?? 0}/${o.subscription?.limits?.beds ?? '—'}`],
                    ['Remaining', o.subscription?.days_remaining != null
                      ? `${o.subscription.days_remaining}d` : '—']].map(([k, v]) => (
                    <div key={k}>
                      <p className="text-2xs text-slate-500">{k}</p>
                      <p className="text-xs font-medium text-slate-900 tnum">{v}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            empty={<EmptyState icon={Building} title="No organisations match"
              message="Clear the filters, or create the first PG."
              action={<Link to="/master/organizations/new">
                <Button variant="primary" icon={Plus}>Create a PG</Button></Link>} />} />
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between">
            <p className="text-xs text-slate-500 tnum">
              Page {pagination.page} of {pagination.total_pages} · {pagination.total} organisations
            </p>
            <div className="flex gap-2">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" disabled={page >= pagination.total_pages}
                onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      <ExtendModal org={extendFor} onClose={() => setExtendFor(null)}
        onDone={() => { setExtendFor(null); orgs.reload() }} />
      <ChangePlanModal org={planFor} plans={plans.data || []} onClose={() => setPlanFor(null)}
        onDone={() => { setPlanFor(null); orgs.reload() }} />
    </>
  )
}

/* ------------------------------------------------------------------ extend */
function ExtendModal({ org, onClose, onDone }) {
  const { success, error } = useToast()
  const [days, setDays] = useState('30')
  const [busy, setBusy] = useState(false)
  if (!org) return null

  const submit = async () => {
    setBusy(true)
    try {
      const sub = await organizationApi.extend(org.id, Number(days))
      success(`${org.name} extended`, `Now runs to ${dateFmt(sub.end_date)}.`)
      onDone()
    } catch (err) {
      error('Could not extend', err.message)
    } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={onClose} size="sm" title={`Extend ${org.name}`}
      subtitle={org.subscription
        ? `Currently expires ${dateFmt(org.subscription.end_date)}` : undefined}
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} onClick={submit}>Extend</Button></>}>
      <div className="space-y-4">
        <FormField label="Extend by" required>
          <Select value={days} onChange={(e) => setDays(e.target.value)}>
            {[30, 60, 90, 180, 365].map((d) => (
              <option key={d} value={d}>{d} days</option>
            ))}
          </Select>
        </FormField>
        <InlineAlert tone="info">
          An expired subscription is extended from today; a live one is extended from its
          current end date, so no unused time is lost.
        </InlineAlert>
      </div>
    </Modal>
  )
}

/* ------------------------------------------------------------- change plan */
function ChangePlanModal({ org, plans, onClose, onDone }) {
  const { success, error } = useToast()
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  if (!org) return null

  const target = plans.find((p) => p.code === code)

  const submit = async () => {
    if (!code) return error('Choose a plan.')
    setBusy(true)
    try {
      await organizationApi.changePlan(org.id, code)
      success(`${org.name} moved to ${target?.name}`)
      onDone()
    } catch (err) {
      error('Could not change the plan', err.message)
    } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={onClose} size="sm" title={`Change plan for ${org.name}`}
      subtitle={`Currently on ${org.subscription?.plan_name || 'no plan'}`}
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} onClick={submit}>Change plan</Button></>}>
      <div className="space-y-4">
        <FormField label="New plan" required>
          <Select value={code} onChange={(e) => setCode(e.target.value)}>
            <option value="">Choose…</option>
            {plans.map((p) => (
              <option key={p.code} value={p.code}>{p.name} — {inr(p.price)}/mo</option>
            ))}
          </Select>
        </FormField>

        {target && (
          <div className="rounded-lg border border-line bg-slate-50 p-3.5">
            <p className="text-xs font-medium text-slate-700 mb-2">Limits on {target.name}</p>
            <dl className="grid grid-cols-2 gap-y-1.5 gap-x-4">
              {['branches', 'rooms', 'beds', 'customers', 'users'].map((k) => (
                <div key={k} className="flex justify-between text-xs">
                  <dt className="text-slate-500 capitalize">{k}</dt>
                  <dd className="tnum text-slate-900">
                    {org.counts?.[k] ?? 0} / {target.limits[k]}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        <InlineAlert tone="warn">
          A downgrade is refused if current usage would exceed the new plan's limits —
          the server checks before anything changes.
        </InlineAlert>
      </div>
    </Modal>
  )
}
