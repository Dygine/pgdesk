import { Link } from 'react-router-dom'
import {
  Building2, BedDouble, DoorOpen, Users, Layers3, TrendingUp, Plus, Gauge,
} from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { dashboardApi } from '@/services/api/dashboardApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, Button, StatCard, StatusBadge, EmptyState, ProgressBar,
  Skeleton, InlineAlert,
} from '@/components/ui'
import { ChartCard, DonutChart, HBarChart } from '@/components/charts/Charts'
import { num, relative } from '@/lib/format'
import { ShareBedsCard } from './ShareBeds'

const BED_COLOR = {
  occupied: '#373DA6', available: '#0F766E', reserved: '#B45309',
  maintenance: '#BE123C', blocked: '#64748B',
}

export default function OwnerDashboard() {
  const { user, activeBranchId, branchScope } = useAuth()
  const dash = useApi(() => dashboardApi.overview(activeBranchId), [activeBranchId])
  const plan = useApi(() => subscriptionApi.mine(), [])

  const d = dash.data
  const p = d?.property

  if (dash.error) {
    return (<><PageHeader title="Dashboard" />
      <InlineAlert tone="error" title="Could not load">{dash.error.message}</InlineAlert></>)
  }

  return (
    <>
      <PageHeader
        title={`Good to see you, ${user?.name?.split(' ')[0] || 'there'}`}
        subtitle={branchScope === 'all'
          ? 'Across every branch you can see.'
          : `Filtered to one branch. Use the selector to widen it.`}
        actions={<PermissionGuard perm="rooms.create">
          <Link to="/app/rooms"><Button variant="primary" icon={Plus}>Add a room</Button></Link>
        </PermissionGuard>} />

      {dash.loading && !d ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[104px]" />)}
        </div>
      ) : d && (
        <>
          <ShareBedsCard byBranch={d.by_branch || []} />

          {/* Hero: occupancy at a glance - the first thing an owner should see. */}
          <Card className="mb-4">
            <div className="p-5 sm:p-6 flex flex-col sm:flex-row items-center gap-6">
              <DonutChart size={172} thickness={18}
                centerValue={`${p.occupancy_rate}%`} centerLabel="occupied"
                segments={[
                  { label: 'Occupied', value: p.occupied_beds, color: '#373DA6' },
                  { label: 'Available', value: p.available_beds, color: '#0F766E' },
                ]} />
              <div className="flex-1 w-full grid grid-cols-3 gap-3 sm:gap-4">
                <Link to="/app/beds" className="rounded-xl bg-emerald-50 p-4 hover:bg-emerald-100 transition-colors">
                  <p className="text-2xs font-semibold text-emerald-700 uppercase tracking-wide">Available</p>
                  <p className="text-2xl font-semibold text-emerald-800 tnum mt-1">{num(p.available_beds)}</p>
                  <p className="text-2xs text-emerald-600 mt-0.5">ready to sell</p>
                </Link>
                <div className="rounded-xl bg-violet-50 p-4">
                  <p className="text-2xs font-semibold text-violet-700 uppercase tracking-wide">Residents</p>
                  <p className="text-2xl font-semibold text-violet-800 tnum mt-1">{num(d.people.customers)}</p>
                  <p className="text-2xs text-violet-600 mt-0.5">living here now</p>
                </div>
                <Link to="/app/users" className="rounded-xl bg-blue-50 p-4 hover:bg-blue-100 transition-colors">
                  <p className="text-2xs font-semibold text-blue-700 uppercase tracking-wide">Staff</p>
                  <p className="text-2xl font-semibold text-blue-800 tnum mt-1">{num(d.people.active_staff)}</p>
                  <p className="text-2xs text-blue-600 mt-0.5">on the team</p>
                </Link>
              </div>
            </div>
          </Card>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
            <StatCard label="Branches" value={num(p.branches)} icon={Building2} tone="slate"
              to="/app/branches" />
            <StatCard label="Buildings" value={num(p.buildings)} tone="slate" to="/app/property" />
            <StatCard label="Floors" value={num(p.floors)} icon={Layers3} tone="slate" />
            <StatCard label="Rooms" value={num(p.rooms)} icon={DoorOpen} tone="slate"
              to="/app/rooms" />
          </div>

          <div className="grid lg:grid-cols-2 gap-4 mb-4">
            <ChartCard title="Bed inventory" subtitle="Where every bed currently stands">
              <DonutChart centerValue={p.beds} centerLabel="beds"
                segments={Object.entries(p.bed_status || {})
                  .filter(([, v]) => v > 0)
                  .map(([k, v]) => ({ label: k, value: v, color: BED_COLOR[k] || '#94A3B8' }))} />
            </ChartCard>

            <ChartCard title="Occupancy by branch" subtitle="Percentage of beds filled">
              {d.by_branch.length ? (
                <HBarChart color="#373DA6" valueFormat={(v) => `${v}%`}
                  data={d.by_branch.map((b) => ({ label: b.name, value: b.occupancy_rate }))} />
              ) : <EmptyState compact title="No branches to compare" />}
            </ChartCard>
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader title="Branches" subtitle="Only those you are assigned to"
                action={<Link to="/app/branches"><Button size="sm">Manage</Button></Link>} />
              {d.by_branch.length === 0 ? (
                <EmptyState icon={Building2} compact title="No branches yet"
                  message="Create one to start adding rooms and beds." />
              ) : (
                <div className="divide-y divide-line">
                  {d.by_branch.map((b) => (
                    <div key={b.id} className="px-5 py-3.5">
                      <div className="flex items-center justify-between gap-3 mb-2">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-slate-900 truncate">{b.name}</p>
                          <p className="text-2xs text-slate-500 tnum">
                            {b.rooms} rooms · {b.beds} beds · {b.available} available
                          </p>
                        </div>
                        <span className="text-sm font-semibold text-slate-900 tnum shrink-0">
                          {b.occupancy_rate}%
                        </span>
                      </div>
                      <ProgressBar value={b.occupied} max={b.beds || 1} />
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <CardHeader title="Recent activity" subtitle="From the audit log" />
              {d.recent_activity.length === 0 ? (
                <EmptyState compact title="Nothing logged yet" />
              ) : (
                <div className="divide-y divide-line max-h-[400px] overflow-y-auto">
                  {d.recent_activity.map((a) => (
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

          {plan.data && (
            <Card className="mt-4">
              <CardHeader title="Plan usage" subtitle={`${plan.data.plan || 'No plan'} · ${plan.data.days_remaining ?? '—'} days remaining`} />
              <div className="p-5 grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {plan.data.detail.filter((x) => x.limit && x.used > 0).map((x) => (
                  <div key={x.key}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-slate-600 capitalize">{x.plural}</span>
                      <span className="tnum text-slate-900">{x.used}/{x.limit}</span>
                    </div>
                    <ProgressBar value={x.used} max={x.limit}
                      tone={x.severity === 'critical' ? 'rose'
                        : x.severity === 'high' || x.severity === 'warn' ? 'amber' : 'brand'} />
                  </div>
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </>
  )
}
