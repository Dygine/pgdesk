import { useState } from 'react'
import { CalendarCheck, Check } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { attendanceApi } from '@/services/api/attendanceApi'
import { residentApi } from '@/services/api/residentApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, Button, DataTable, StatusBadge, FilterBar, EmptyState,
  StatCard, InlineAlert, Skeleton, Input, FormField,
} from '@/components/ui'
import { num, dateFmt, timeFmt, today } from '@/lib/format'

const STATUSES = ['PRESENT', 'ABSENT', 'LATE', 'ON_LEAVE']
const TONE = { PRESENT: 'emerald', ABSENT: 'rose', LATE: 'amber', ON_LEAVE: 'blue' }

export default function Attendance() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [onDate, setOnDate] = useState(today())
  const [status, setStatus] = useState('all')
  const [busy, setBusy] = useState(null)

  const residents = useApi(
    () => residentApi.list({ status: 'live', branch_id: activeBranchId, page_size: 200 }),
    [activeBranchId], { enabled: can('customers.view') })
  const attendance = useApi(
    () => attendanceApi.list({ on_date: onDate, subject: 'RESIDENT',
      branch_id: activeBranchId, status, page_size: 300 }),
    [onDate, activeBranchId, status])

  const rows = attendance.data?.items || []
  const marked = new Map(rows.map((r) => [r.resident_id, r]))
  const roster = (residents.data?.items || []).filter((r) => r.status === 'ACTIVE')
  const counts = STATUSES.reduce(
    (acc, s) => ({ ...acc, [s]: rows.filter((r) => r.status === s).length }), {})

  const mark = async (resident, value) => {
    setBusy(resident.id)
    try {
      await attendanceApi.mark({ resident_id: resident.id, on_date: onDate, status: value })
      success(`${resident.full_name} marked ${value.toLowerCase().replace('_', ' ')}`)
      attendance.reload()
    } catch (err) { error('Could not record that', err.message) }
    finally { setBusy(null) }
  }

  return (
    <>
      <PageHeader title="Attendance"
        subtitle="Who is in today. Gate scans mark residents present automatically." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Present" value={num(counts.PRESENT || 0)}
          icon={CalendarCheck} tone="emerald"
          sub={roster.length ? `of ${roster.length} residents` : undefined} />
        <StatCard label="Absent" value={num(counts.ABSENT || 0)} tone="rose" />
        <StatCard label="Late" value={num(counts.LATE || 0)} tone="amber" />
        <StatCard label="On leave" value={num(counts.ON_LEAVE || 0)} tone="blue" />
      </div>

      <Card className="mb-4">
        <div className="p-4 flex flex-col sm:flex-row gap-3 sm:items-end">
          <FormField label="Date" className="sm:w-56">
            <Input type="date" value={onDate} onChange={(e) => setOnDate(e.target.value)} />
          </FormField>
          <div className="flex-1">
            <FilterBar filters={[{ key: 'status', label: 'Status', value: status,
              onChange: setStatus, options: STATUSES }]} />
          </div>
        </div>
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Mark the roll" subtitle={dateFmt(onDate)} />
          {residents.loading ? <div className="p-4"><Skeleton className="h-48" /></div>
            : roster.length === 0 ? (
              <EmptyState compact title="No active residents" />
            ) : (
              <div className="divide-y divide-line max-h-[520px] overflow-y-auto">
                {roster.map((r) => {
                  const existing = marked.get(r.id)
                  return (
                    <div key={r.id} className="px-5 py-2.5 flex items-center gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-slate-800 truncate">{r.full_name}</p>
                        <p className="text-2xs text-slate-500">
                          {r.placement?.room ? `Room ${r.placement.room}` : 'No room'}
                        </p>
                      </div>
                      <PermissionGuard perm={['attendance.mark', 'attendance.manage']}>
                        <div className="flex gap-1 shrink-0">
                          {STATUSES.map((s) => (
                            <button key={s} disabled={busy === r.id}
                              onClick={() => mark(r, s)}
                              title={s.replace('_', ' ')}
                              className={`h-7 px-2 rounded-md text-2xs font-medium border transition-colors ${
                                existing?.status === s
                                  ? 'border-brand-300 bg-brand-50 text-brand-800'
                                  : 'border-line bg-white text-slate-500 hover:bg-slate-50'}`}>
                              {s[0]}{s === 'ON_LEAVE' ? 'L' : ''}
                            </button>
                          ))}
                        </div>
                      </PermissionGuard>
                    </div>
                  )
                })}
              </div>
            )}
        </Card>

        <Card>
          <CardHeader title="Recorded" subtitle={`${rows.length} entries for ${dateFmt(onDate)}`} />
          {attendance.error ? (
            <InlineAlert tone="error" className="m-4">{attendance.error.message}</InlineAlert>
          ) : rows.length === 0 ? (
            <EmptyState icon={CalendarCheck} compact title="Nothing recorded"
              message="Mark the roll on the left, or let gate scans do it." />
          ) : (
            <div className="divide-y divide-line max-h-[520px] overflow-y-auto">
              {rows.map((a) => (
                <div key={a.id} className="px-5 py-2.5 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm text-slate-800 truncate">{a.person}</p>
                    <p className="text-2xs text-slate-500 tnum">
                      {a.check_in_at ? `In ${timeFmt(a.check_in_at)}` : 'No entry time'}
                      {a.source === 'gate' ? ' · from the gate' : ''}
                    </p>
                  </div>
                  <StatusBadge status={a.status.replace('_', ' ')} tone={TONE[a.status]} dot />
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
