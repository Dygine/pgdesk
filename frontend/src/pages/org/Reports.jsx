import { useState } from 'react'
import { BarChart3, Download } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { reportApi } from '@/services/api/reportApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, Button, DataTable, EmptyState, Skeleton, InlineAlert,
  FormField, Input, StatusBadge,
} from '@/components/ui'
import { today } from '@/lib/format'

const ago = (days) => {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

/** Every figure is aggregated by PostgreSQL, so totals cover the whole set. */
export default function Reports() {
  const { activeBranchId } = useAuth()
  const { success, error } = useToast()
  const [key, setKey] = useState('occupancy')
  const [fromDate, setFromDate] = useState(ago(30))
  const [toDate, setToDate] = useState(today())
  const [busy, setBusy] = useState(false)

  const catalogue = useApi(() => reportApi.catalogue(), [], { initial: [] })
  const report = useApi(
    () => reportApi.run(key, { branch_id: activeBranchId, from_date: fromDate, to_date: toDate }),
    [key, activeBranchId, fromDate, toDate])

  const groups = (catalogue.data || []).reduce((acc, r) => {
    (acc[r.group] ||= []).push(r)
    return acc
  }, {})

  const download = async () => {
    setBusy(true)
    try {
      await reportApi.downloadCsv(key, {
        branch_id: activeBranchId, from_date: fromDate, to_date: toDate })
      success('CSV downloaded')
    } catch (err) { error('Export failed', err.message) }
    finally { setBusy(false) }
  }

  const columns = (report.data?.columns || []).map((c) => ({
    key: c.key, header: c.label,
    align: typeof report.data?.rows?.[0]?.[c.key] === 'number' ? 'right' : 'left',
    render: (row) => (
      <span className={typeof row[c.key] === 'number' ? 'tnum text-slate-800' : 'text-slate-700'}>
        {row[c.key] ?? '—'}
      </span>
    ),
  }))

  return (
    <>
      <PageHeader title="Reports"
        subtitle="Aggregated on the server, so the totals cover everything — not just this page."
        actions={<PermissionGuard perm="reports.export">
          <Button icon={Download} loading={busy} onClick={download}>Export CSV</Button>
        </PermissionGuard>} />

      <div className="grid lg:grid-cols-[260px_minmax(0,1fr)] gap-4">
        <div className="space-y-4">
          <Card>
            <CardHeader title="Period" />
            <div className="p-4 space-y-3">
              <FormField label="From">
                <Input type="date" value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)} />
              </FormField>
              <FormField label="To">
                <Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
              </FormField>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {[['7d', 7], ['30d', 30], ['90d', 90], ['1y', 365]].map(([label, days]) => (
                  <Button key={label} size="sm"
                    onClick={() => { setFromDate(ago(days)); setToDate(today()) }}>
                    {label}
                  </Button>
                ))}
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader title="Reports" subtitle={`${(catalogue.data || []).length} available`} />
            {catalogue.loading ? <div className="p-4"><Skeleton className="h-40" /></div> : (
              <div className="p-2">
                {Object.entries(groups).map(([group, items]) => (
                  <div key={group} className="mb-2">
                    <p className="px-2 py-1 text-2xs font-semibold uppercase tracking-wide text-slate-400">
                      {group}
                    </p>
                    {items.map((r) => (
                      <button key={r.key} onClick={() => setKey(r.key)}
                        className={`w-full text-left px-2.5 py-2 rounded-md text-sm transition-colors ${
                          key === r.key ? 'bg-brand-50 text-brand-800 font-medium'
                            : 'text-slate-600 hover:bg-slate-50'}`}>
                        {r.label}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <Card>
          <CardHeader title={report.data?.label || 'Report'}
            subtitle={report.data
              ? `${report.data.row_count} row${report.data.row_count === 1 ? '' : 's'} · ${report.data.from_date} to ${report.data.to_date}`
              : undefined}
            action={report.data && <StatusBadge status={`${report.data.row_count} rows`}
              tone="slate" />} />

          {report.error ? (
            <InlineAlert tone="error" className="m-4">{report.error.message}</InlineAlert>
          ) : report.loading && !report.data ? (
            <div className="p-4 space-y-2">{[0, 1, 2, 3].map((i) =>
              <Skeleton key={i} className="h-10" />)}</div>
          ) : (report.data?.rows || []).length === 0 ? (
            <EmptyState icon={BarChart3} title="Nothing in this period"
              message="Widen the dates, or pick a different report." />
          ) : (
            <DataTable columns={columns} rows={report.data.rows} pageSize={50}
              mobileCard={(row) => (
                <div className="space-y-1">
                  {report.data.columns.slice(0, 4).map((c) => (
                    <div key={c.key} className="flex justify-between gap-3 text-xs">
                      <span className="text-slate-500">{c.label}</span>
                      <span className="tnum text-slate-900 truncate">{row[c.key] ?? '—'}</span>
                    </div>
                  ))}
                </div>
              )} />
          )}
        </Card>
      </div>
    </>
  )
}
