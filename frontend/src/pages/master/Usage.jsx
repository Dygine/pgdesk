import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Gauge, TriangleAlert } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, StatCard, StatusBadge, EmptyState, ProgressBar, FilterBar,
  Skeleton, InlineAlert,
} from '@/components/ui'
import { num } from '@/lib/format'

const TONE = { ok: 'emerald', warn: 'amber', high: 'amber', critical: 'rose' }

export default function Usage() {
  const [severity, setSeverity] = useState('all')
  const [search, setSearch] = useState('')
  const usage = useApi(() => subscriptionApi.usage(severity), [severity])

  const rows = (usage.data || []).filter(
    (r) => !search || r.organization_name.toLowerCase().includes(search.toLowerCase()))

  const counts = (usage.data || []).reduce((acc, r) => {
    acc[r.worst_severity] = (acc[r.worst_severity] || 0) + 1
    return acc
  }, {})

  return (
    <>
      <PageHeader title="Usage monitoring"
        subtitle="Where each tenant sits against the limits their plan allows." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Organisations" value={num((usage.data || []).length)} icon={Gauge} tone="brand" />
        <StatCard label="Comfortable" value={num(counts.ok || 0)} tone="emerald" />
        <StatCard label="Approaching a limit"
          value={num((counts.warn || 0) + (counts.high || 0))} tone="amber" />
        <StatCard label="At a limit" value={num(counts.critical || 0)}
          icon={TriangleAlert} tone={counts.critical ? 'rose' : 'slate'} />
      </div>

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={setSearch} searchPlaceholder="Search organisation…"
            filters={[{ key: 'severity', label: 'Severity', value: severity,
              onChange: setSeverity, options: ['ok', 'warn', 'high', 'critical'] }]} />
        </div>

        {usage.error ? (
          <InlineAlert tone="error" className="m-4">{usage.error.message}</InlineAlert>
        ) : usage.loading && !usage.data ? (
          <div className="p-4 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-32" />)}</div>
        ) : rows.length === 0 ? (
          <EmptyState icon={Gauge} title="Nothing matches"
            message="No organisation sits at that severity right now." />
        ) : (
          <div className="divide-y divide-line">
            {rows.map((r) => (
              <div key={r.organization_id} className="p-4 sm:p-5">
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <Link to={`/master/organizations/${r.organization_id}`}
                      className="text-sm font-semibold text-slate-900 hover:text-brand-800">
                      {r.organization_name}
                    </Link>
                    <p className="text-xs text-slate-500">
                      {r.plan || 'No plan'}
                      {r.days_remaining != null && ` · ${r.days_remaining} days remaining`}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <StatusBadge status={r.status} dot />
                    <StatusBadge status={r.worst_severity} tone={TONE[r.worst_severity]} />
                  </div>
                </div>

                <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
                  {r.detail.filter((d) => d.limit).map((d) => (
                    <div key={d.key}>
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <p className="text-xs text-slate-600 capitalize">{d.plural}</p>
                        <p className="text-xs tnum text-slate-900">{d.used}/{d.limit}</p>
                      </div>
                      <ProgressBar value={d.used} max={d.limit} tone={TONE[d.severity]} />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </>
  )
}
