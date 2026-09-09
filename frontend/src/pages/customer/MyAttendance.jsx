import { CalendarCheck } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { meApi } from '@/services/api/meApi'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, StatCard, StatusBadge, EmptyState, Skeleton, InlineAlert,
} from '@/components/ui'
import { num, dateFmt, timeFmt } from '@/lib/format'

const TONE = { PRESENT: 'emerald', ABSENT: 'rose', LATE: 'amber', ON_LEAVE: 'blue' }

export default function MyAttendance() {
  const { data, loading, error } = useApi(() => meApi.attendance(60), [])

  if (error) {
    return (<><PageHeader title="My attendance" />
      <InlineAlert tone="error" title="Could not load">{error.message}</InlineAlert></>)
  }
  if (loading && !data) {
    return (<><PageHeader title="My attendance" /><Skeleton className="h-64" /></>)
  }

  const s = data.summary
  const total = Object.values(s).reduce((a, b) => a + b, 0)

  return (
    <>
      <PageHeader title="My attendance"
        subtitle={`The last ${data.days} days. Entry scans at the gate mark you present automatically.`} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Present" value={num(s.PRESENT || 0)} icon={CalendarCheck}
          tone="emerald" sub={total ? `${Math.round((s.PRESENT || 0) / total * 100)}% of days` : undefined} />
        <StatCard label="Absent" value={num(s.ABSENT || 0)} tone="rose" />
        <StatCard label="Late" value={num(s.LATE || 0)} tone="amber" />
        <StatCard label="On leave" value={num(s.ON_LEAVE || 0)} tone="blue" />
      </div>

      <Card>
        <CardHeader title="Day by day" subtitle={`${data.records.length} records`} />
        {data.records.length === 0 ? (
          <EmptyState icon={CalendarCheck} title="Nothing recorded yet"
            message="Your attendance appears here once you start scanning at the gate." />
        ) : (
          <div className="divide-y divide-line max-h-[600px] overflow-y-auto">
            {data.records.map((r) => (
              <div key={r.on_date} className="px-5 py-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-slate-800 tnum">{dateFmt(r.on_date)}</p>
                  <p className="text-2xs text-slate-500">
                    {r.check_in_at ? `In ${timeFmt(r.check_in_at)}` : 'No entry recorded'}
                    {r.check_out_at ? ` · Out ${timeFmt(r.check_out_at)}` : ''}
                    {r.source === 'gate' ? ' · from the gate' : ''}
                  </p>
                </div>
                <StatusBadge status={r.status.replace('_', ' ')} tone={TONE[r.status]} dot />
              </div>
            ))}
          </div>
        )}
      </Card>
    </>
  )
}
