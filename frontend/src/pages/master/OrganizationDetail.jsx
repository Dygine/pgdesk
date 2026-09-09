import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft, Building2, CalendarPlus, ShieldOff, ShieldCheck, Mail, Phone, MapPin, Gauge,
} from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { organizationApi } from '@/services/api/organizationApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, StatusBadge, Tabs, EmptyState, ProgressBar, StatCard,
  Modal, FormField, Select, InlineAlert, Skeleton, DataTable,
} from '@/components/ui'
import { inr, num, dateFmt, relative } from '@/lib/format'

const SEVERITY_TONE = { ok: 'emerald', warn: 'amber', high: 'amber', critical: 'rose' }

export default function OrganizationDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { success, error } = useToast()
  const [tab, setTab] = useState('overview')
  const [extendOpen, setExtendOpen] = useState(false)
  const [planOpen, setPlanOpen] = useState(false)

  const org = useApi(() => organizationApi.get(id), [id])
  const plans = useApi(() => subscriptionApi.plans(), [])
  const audit = useApi(() => organizationApi.list && null, [])   // placeholder, see Activity tab

  const o = org.data

  const act = async (fn, message) => {
    try { await fn(); success(message); org.reload() }
    catch (err) { error('That did not work', err.message) }
  }

  if (org.loading && !o) {
    return (<><PageHeader title="Organisation" /><Skeleton className="h-64" /></>)
  }
  if (org.error) {
    return (<><PageHeader title="Organisation" />
      <InlineAlert tone="error" title="Could not load">{org.error.message}</InlineAlert></>)
  }
  if (!o) return null

  const usage = o.usage
  const sub = o.subscription

  return (
    <>
      <PageHeader
        breadcrumb={<><Link to="/master/organizations" className="hover:text-slate-800">Organisations</Link>
          <span>/</span><span className="text-slate-700">{o.name}</span></>}
        title={o.name}
        subtitle={`${o.city || '—'} · ${o.pg_type || 'PG'} · owner ${o.owner_name}`}
        actions={<>
          <Button icon={ArrowLeft} onClick={() => navigate('/master/organizations')}
            className="hidden sm:inline-flex">Back</Button>
          <Button icon={CalendarPlus} onClick={() => setExtendOpen(true)}>Extend</Button>
          {o.status === 'SUSPENDED' ? (
            <Button variant="success" icon={ShieldCheck}
              onClick={() => act(() => organizationApi.setStatus(o.id, 'ACTIVE'),
                `${o.name} reactivated.`)}>Reactivate</Button>
          ) : (
            <Button variant="danger" icon={ShieldOff}
              onClick={() => act(() => organizationApi.setStatus(o.id, 'SUSPENDED'),
                `${o.name} suspended.`)}>Suspend</Button>
          )}
        </>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Status" value={o.status} icon={Building2}
          tone={o.status === 'ACTIVE' ? 'emerald' : o.status === 'TRIAL' ? 'blue'
            : o.status === 'SUSPENDED' || o.status === 'EXPIRED' ? 'rose' : 'amber'} />
        <StatCard label="Plan" value={sub?.plan_name || '—'} tone="brand"
          sub={sub ? `${inr(plans.data?.find((p) => p.code === sub.plan_code)?.price || 0)}/mo` : undefined} />
        <StatCard label="Expires" value={sub ? dateFmt(sub.end_date) : '—'}
          tone={sub && sub.days_remaining < 0 ? 'rose' : sub && sub.days_remaining <= 30 ? 'amber' : 'slate'}
          sub={sub ? `${sub.days_remaining} days remaining` : undefined} />
        <StatCard label="Beds" value={num(o.counts?.beds ?? 0)} tone="violet"
          sub={`${o.counts?.branches ?? 0} branches · ${o.counts?.rooms ?? 0} rooms`} />
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'overview', label: 'Overview' },
        { value: 'usage', label: 'Usage' },
        { value: 'branches', label: 'Branches', count: o.branches?.length },
        { value: 'users', label: 'Users', count: o.users?.length },
        { value: 'history', label: 'Subscription history', count: o.subscription_history?.length },
      ]} />

      <div className="mt-4">
        {tab === 'overview' && (
          <div className="grid lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader title="Organisation" />
              <dl className="divide-y divide-line">
                {[['Registered name', o.legal_name], ['Type', o.pg_type], ['Accepts', o.gender],
                  ['GSTIN', o.gstin], ['Address', o.address], ['City', o.city],
                  ['State', o.state], ['Pincode', o.pincode],
                  ['Onboarded', o.onboarded_on ? dateFmt(o.onboarded_on) : null],
                  ['Notes', o.notes]].map(([k, v]) => (
                  <div key={k} className="px-5 py-2.5 grid grid-cols-3 gap-3">
                    <dt className="text-xs text-slate-500">{k}</dt>
                    <dd className="col-span-2 text-sm text-slate-800">{v || '—'}</dd>
                  </div>
                ))}
              </dl>
            </Card>

            <Card>
              <CardHeader title="Owner" subtitle="Holds the system Owner role" />
              <div className="p-5 space-y-2">
                <p className="text-base font-medium text-slate-900">{o.owner_name}</p>
                <p className="flex items-center gap-2 text-sm text-slate-600">
                  <Mail size={14} className="text-slate-400" />{o.owner_email}</p>
                <p className="flex items-center gap-2 text-sm text-slate-600">
                  <Phone size={14} className="text-slate-400" />{o.owner_phone || '—'}</p>
                <p className="flex items-center gap-2 text-sm text-slate-600">
                  <MapPin size={14} className="text-slate-400" />{o.city || '—'}</p>
                <div className="pt-3">
                  <Button size="sm" onClick={() => setPlanOpen(true)}>Change plan</Button>
                </div>
              </div>
            </Card>
          </div>
        )}

        {tab === 'usage' && usage && (
          <Card>
            <CardHeader title="Usage against plan limits"
              subtitle={`${usage.plan || 'No plan'} · worst: ${usage.worst_severity}`} />
            <div className="p-5 grid sm:grid-cols-2 gap-4">
              {usage.detail.map((d) => (
                <div key={d.key} className="rounded-lg border border-line p-4">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <p className="text-sm font-medium text-slate-900">{d.plural}</p>
                    <StatusBadge status={d.severity} tone={SEVERITY_TONE[d.severity]} />
                  </div>
                  <p className="text-lg font-semibold text-slate-900 tnum">
                    {d.used}<span className="text-sm font-normal text-slate-500"> / {d.limit ?? '∞'}</span>
                  </p>
                  {d.limit ? <ProgressBar value={d.used} max={d.limit} className="mt-2"
                    tone={SEVERITY_TONE[d.severity]} /> : null}
                </div>
              ))}
            </div>
          </Card>
        )}

        {tab === 'branches' && (
          <Card>
            <CardHeader title="Branches" />
            {!o.branches?.length ? (
              <EmptyState icon={Building2} title="No branches yet"
                message="The owner creates branches from their own portal." />
            ) : (
              <DataTable rows={o.branches} pageSize={10}
                columns={[
                  { key: 'name', header: 'Branch',
                    render: (b) => <div><p className="font-medium text-slate-900">{b.name}</p>
                      <p className="text-xs text-slate-500">{b.code} · {b.city || '—'}</p></div> },
                  { key: 'rooms', header: 'Rooms', align: 'right',
                    render: (b) => <span className="tnum text-slate-700">{b.rooms}</span> },
                  { key: 'beds', header: 'Beds', align: 'right',
                    render: (b) => <span className="tnum text-slate-700">{b.beds}</span> },
                  { key: 'status', header: 'Status',
                    render: (b) => <StatusBadge status={b.status} dot /> },
                ]}
                mobileCard={(b) => (
                  <div className="flex items-center justify-between gap-3">
                    <div><p className="text-sm font-medium text-slate-900">{b.name}</p>
                      <p className="text-xs text-slate-500 tnum">{b.rooms} rooms · {b.beds} beds</p></div>
                    <StatusBadge status={b.status} />
                  </div>
                )} />
            )}
          </Card>
        )}

        {tab === 'users' && (
          <Card>
            <CardHeader title="Users" subtitle="Staff accounts inside this organisation" />
            {!o.users?.length ? <EmptyState title="No users" compact /> : (
              <DataTable rows={o.users} pageSize={10}
                columns={[
                  { key: 'name', header: 'User',
                    render: (u) => <div><p className="font-medium text-slate-900">{u.name}</p>
                      <p className="text-xs text-slate-500">{u.email}</p></div> },
                  { key: 'roles', header: 'Roles', sortable: false,
                    render: (u) => <span className="text-sm text-slate-700">
                      {u.roles.join(', ') || '—'}</span> },
                  { key: 'last_login_at', header: 'Last seen',
                    render: (u) => <span className="text-xs text-slate-500">
                      {u.last_login_at ? relative(u.last_login_at) : 'Never'}</span> },
                  { key: 'status', header: 'Status',
                    render: (u) => <StatusBadge status={u.status} dot /> },
                ]}
                mobileCard={(u) => (
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-900 truncate">{u.name}</p>
                      <p className="text-xs text-slate-500 truncate">{u.roles.join(', ')}</p>
                    </div>
                    <StatusBadge status={u.status} />
                  </div>
                )} />
            )}
          </Card>
        )}

        {tab === 'history' && (
          <Card>
            <CardHeader title="Subscription history" />
            {!o.subscription_history?.length ? <EmptyState title="No history" compact /> : (
              <div className="divide-y divide-line">
                {o.subscription_history.map((s) => (
                  <div key={s.id} className="px-5 py-3.5 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-slate-900">{s.plan}</p>
                      <p className="text-xs text-slate-500 tnum">
                        {dateFmt(s.start_date)} → {dateFmt(s.end_date)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {s.is_current && <StatusBadge status="Current" tone="brand" />}
                      <StatusBadge status={s.status} dot />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}
      </div>

      <ExtendModal open={extendOpen} org={o} onClose={() => setExtendOpen(false)}
        onDone={() => { setExtendOpen(false); org.reload() }} />
      <PlanModal open={planOpen} org={o} plans={plans.data || []}
        onClose={() => setPlanOpen(false)}
        onDone={() => { setPlanOpen(false); org.reload() }} />
    </>
  )
}

function ExtendModal({ open, org, onClose, onDone }) {
  const { success, error } = useToast()
  const [days, setDays] = useState('30')
  const [busy, setBusy] = useState(false)
  if (!open) return null

  const submit = async () => {
    setBusy(true)
    try {
      const sub = await organizationApi.extend(org.id, Number(days))
      success('Subscription extended', `Now runs to ${dateFmt(sub.end_date)}.`)
      onDone()
    } catch (err) { error('Could not extend', err.message) } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={onClose} size="sm" title={`Extend ${org.name}`}
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} onClick={submit}>Extend</Button></>}>
      <FormField label="Extend by" required>
        <Select value={days} onChange={(e) => setDays(e.target.value)}>
          {[30, 60, 90, 180, 365].map((d) => <option key={d} value={d}>{d} days</option>)}
        </Select>
      </FormField>
    </Modal>
  )
}

function PlanModal({ open, org, plans, onClose, onDone }) {
  const { success, error } = useToast()
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  if (!open) return null

  const submit = async () => {
    if (!code) return error('Choose a plan.')
    setBusy(true)
    try {
      await organizationApi.changePlan(org.id, code)
      success('Plan changed')
      onDone()
    } catch (err) { error('Could not change the plan', err.message) } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={onClose} size="sm" title="Change plan"
      subtitle={`Currently on ${org.subscription?.plan_name || 'no plan'}`}
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} onClick={submit}>Change plan</Button></>}>
      <div className="space-y-4">
        <FormField label="New plan" required>
          <Select value={code} onChange={(e) => setCode(e.target.value)}>
            <option value="">Choose…</option>
            {plans.map((p) => <option key={p.code} value={p.code}>{p.name} — {inr(p.price)}/mo</option>)}
          </Select>
        </FormField>
        <InlineAlert tone="warn">
          A downgrade below current usage is refused by the server before anything changes.
        </InlineAlert>
      </div>
    </Modal>
  )
}
