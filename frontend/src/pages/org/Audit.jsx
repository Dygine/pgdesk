import { useState } from 'react'
import { ScrollText } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { auditApi } from '@/services/api/auditApi'
import { PageHeader } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard,
  InlineAlert, Skeleton,
} from '@/components/ui'
import { num, relative, dateTimeFmt } from '@/lib/format'

/**
 * Tenant-scoped audit.
 *
 * The API filters by the caller's organisation, so an owner sees their own
 * activity and only a master admin sees the platform-wide log.
 */
export default function Audit() {
  const [module, setModule] = useState('all')
  const [page, setPage] = useState(1)
  const audit = useApi(() => auditApi.list({ module, page, page_size: 25 }), [module, page])

  const rows = audit.data?.items || []
  const pagination = audit.data?.pagination
  const modules = [...new Set(rows.map((a) => a.module))].sort()

  return (
    <>
      <PageHeader title="Audit log"
        subtitle="Every state change, written by the API inside the same transaction." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Entries" value={num(pagination?.total ?? 0)}
          icon={ScrollText} tone="brand" />
        <StatCard label="Modules in view" value={num(modules.length)} tone="violet" />
        <StatCard label="People acting"
          value={num(new Set(rows.map((a) => a.user_name)).size)} tone="emerald" />
        <StatCard label="Page"
          value={`${pagination?.page ?? 1}/${pagination?.total_pages ?? 1}`} tone="slate" />
      </div>

      <InlineAlert tone="info" className="mb-4">
        Passwords, tokens and KYC numbers never reach this log — only what changed,
        who changed it and when.
      </InlineAlert>

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar filters={[{ key: 'module', label: 'Module', value: module,
            onChange: (v) => { setModule(v); setPage(1) }, options: modules }]} />
        </div>

        {audit.error ? (
          <InlineAlert tone="error" className="m-4">{audit.error.message}</InlineAlert>
        ) : audit.loading && !audit.data ? (
          <div className="p-4 space-y-2">{[0, 1, 2, 3].map((i) =>
            <Skeleton key={i} className="h-12" />)}</div>
        ) : (
          <DataTable rows={rows} pageSize={25}
            columns={[
              { key: 'created_at', header: 'When',
                render: (a) => <div><p className="text-sm text-slate-700">{relative(a.created_at)}</p>
                  <p className="text-2xs text-slate-500 tnum">{dateTimeFmt(a.created_at)}</p></div> },
              { key: 'user_name', header: 'Who',
                render: (a) => <span className="text-sm text-slate-800">{a.user_name}</span> },
              { key: 'module', header: 'Module',
                render: (a) => <StatusBadge status={a.module} tone="slate" /> },
              { key: 'action', header: 'Action',
                render: (a) => <StatusBadge status={a.action} tone="brand" /> },
              { key: 'description', header: 'Detail', sortable: false,
                render: (a) => <span className="text-sm text-slate-600">{a.description}</span> },
            ]}
            mobileCard={(a) => (
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <StatusBadge status={a.module} tone="slate" />
                  <StatusBadge status={a.action} tone="brand" />
                </div>
                <p className="text-sm text-slate-800">{a.description}</p>
                <p className="text-2xs text-slate-500">{a.user_name} · {relative(a.created_at)}</p>
              </div>
            )}
            empty={<EmptyState icon={ScrollText} title="Nothing logged yet" />} />
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between">
            <p className="text-xs text-slate-500 tnum">
              Page {pagination.page} of {pagination.total_pages}
            </p>
            <div className="flex gap-2">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" disabled={page >= pagination.total_pages}
                onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>
    </>
  )
}
