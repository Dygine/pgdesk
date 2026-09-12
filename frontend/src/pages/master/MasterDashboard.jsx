import { Link } from 'react-router-dom'
import {
  Building, Users, BedDouble, CreditCard, TrendingUp, TriangleAlert,
  Plus, RefreshCw, Gauge,
} from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { masterApi } from '@/services/api/organizationApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, StatCard, StatusBadge, EmptyState, Skeleton,
  InlineAlert, ProgressBar,
} from '@/components/ui'
import { ChartCard, DonutChart, HBarChart } from '@/components/charts/Charts'
import { inr, num, dateFmt, relative } from '@/lib/format'

/** Platform overview. Every figure is a live aggregate from PostgreSQL. */
export default function MasterDashboard() {
  const { success, error } = useToast()
  const { data, loading, error: failed, reload } = useApi(() => masterApi.dashboard(), [])

  const runSweep = async () => {
    try {
      const res = await subscriptionApi.sweep()
      success('Expiry statuses recomputed',
        `${res.organizations_updated} organisation${res.organizations_updated === 1 ? '' : 's'} updated.`)
      reload()
    } catch (err) {
      error('Could not run the sweep', err.message)
    }
  }

  if (failed) {
    return (
      <>
        <PageHeader title="Platform dashboard" />
        <InlineAlert tone="error" title="Could not load the dashboard">
          {failed.message}
        </InlineAlert>
      </>
    )
  }

  const orgs = data?.organizations
  const platform = data?.platform
  const subs = data?.subscriptions

  return (
    <>
      <PageHeader title="Platform dashboard"
        subtitle="Every PG on PGuru, their subscriptions and what they are running."
        actions={<>
          <Button icon={RefreshCw} onClick={runSweep}>Recompute expiry</Button>
          <Link to="/master/organizations/new">
            <Button variant="primary" icon={Plus}>Create a PG</Button>
          </Link>
        </>} />

      {loading && !data ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[104px]" />)}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
            <StatCard label="Organisations" value={num(orgs.total)} icon={Building} tone="brand"
              sub={`${orgs.active} active · ${orgs.trial} on trial`} to="/master/organizations" />
            <StatCard label="Estimated MRR" value={inr(subs.estimated_mrr)} icon={CreditCard}
              tone="emerald" sub="list price of active plans" to="/master/subscriptions" />
            <StatCard label="Beds under management" value={num(platform.beds)} icon={BedDouble}
              tone="violet" sub={`${platform.occupied_beds} occupied`}
              footer={<ProgressBar value={platform.occupied_beds} max={platform.beds || 1} />} />
            <StatCard label="Residents" value={num(platform.customers)} icon={Users} tone="blue"
              sub={`${platform.occupancy_rate}% occupancy`} />
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
            <StatCard label="Branches" value={num(platform.branches)} tone="slate" />
            <StatCard label="Rooms" value={num(platform.rooms)} tone="slate" />
            <StatCard label="Staff accounts" value={num(platform.users)} tone="slate" />
            <StatCard label="Needs attention"
              value={num(orgs.expired + orgs.suspended + orgs.expiring)}
              icon={TriangleAlert}
              tone={orgs.expired + orgs.suspended ? 'rose' : 'emerald'}
              sub={`${orgs.expiring} expiring · ${orgs.expired} expired · ${orgs.suspended} suspended`}
              to="/master/usage" />
          </div>

          <div className="grid lg:grid-cols-2 gap-4 mb-4">
            <ChartCard title="Subscription health" subtitle="Organisations by status">
              <DonutChart centerValue={orgs.total} centerLabel="organisations"
                segments={[
                  { label: 'Active', value: orgs.active, color: '#0F766E' },
                  { label: 'Trial', value: orgs.trial, color: '#2563EB' },
                  { label: 'Expiring', value: orgs.expiring, color: '#B45309' },
                  { label: 'Expired', value: orgs.expired, color: '#BE123C' },
                  { label: 'Suspended', value: orgs.suspended, color: '#64748B' },
                  { label: 'Inactive', value: orgs.inactive, color: '#94A3B8' },
                ].filter((s) => s.value > 0)} />
            </ChartCard>

            <ChartCard title="Revenue by plan" subtitle="Monthly, at list price">
              {subs.by_plan?.length ? (
                <HBarChart color="#373DA6" valueFormat={inr}
                  data={subs.by_plan.map((p) => ({ label: p.plan, value: p.mrr }))} />
              ) : <EmptyState title="No subscriptions yet" compact />}
            </ChartCard>
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader title="Expiring within 30 days"
                subtitle={`${data.expiring.length} to chase`}
                action={<Link to="/master/subscriptions"><Button size="sm">All plans</Button></Link>} />
              {data.expiring.length === 0 ? (
                <EmptyState icon={Gauge} compact title="Nothing expiring soon"
                  message="Every subscription has more than a month left." />
              ) : (
                <div className="divide-y divide-line">
                  {data.expiring.map((o) => (
                    <Link key={o.id} to={`/master/organizations/${o.id}`}
                      className="px-5 py-3 flex items-center gap-3 hover:bg-slate-50 transition-colors">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-slate-900 truncate">{o.name}</p>
                        <p className="text-xs text-slate-500 tnum">
                          {o.plan} · expires {dateFmt(o.end_date)}
                        </p>
                      </div>
                      <StatusBadge status={`${o.days_remaining}d`}
                        tone={o.days_remaining <= 7 ? 'rose' : 'amber'} />
                    </Link>
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <CardHeader title="Recent platform activity" subtitle="From the audit log"
                action={<Link to="/master/audit"><Button size="sm">Full log</Button></Link>} />
              {data.recent_activity.length === 0 ? (
                <EmptyState compact title="Nothing logged yet" />
              ) : (
                <div className="divide-y divide-line max-h-[420px] overflow-y-auto">
                  {data.recent_activity.map((a) => (
                    <div key={a.id} className="px-5 py-3">
                      <div className="flex items-center gap-2 mb-1">
                        <StatusBadge status={a.module} tone="slate" />
                        <StatusBadge status={a.action} tone="brand" />
                      </div>
                      <p className="text-sm text-slate-700">{a.description}</p>
                      <p className="text-2xs text-slate-400 mt-0.5">
                        {a.user_name} · {relative(a.created_at)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </>
  )
}
