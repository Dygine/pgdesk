import { useState } from 'react'
import { Plus, UserPlus, Check, X, LogIn, LogOut } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { visitorApi } from '@/services/api/visitorApi'
import { residentApi } from '@/services/api/residentApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard, Modal,
  FormField, Input, Select, Textarea, InlineAlert, Skeleton, IconButton,
} from '@/components/ui'
import { num, relative, dateTimeFmt } from '@/lib/format'

const STATUSES = ['PENDING', 'APPROVED', 'INSIDE', 'COMPLETED', 'REJECTED']
const TONE = { PENDING: 'amber', APPROVED: 'emerald', INSIDE: 'brand',
  COMPLETED: 'slate', REJECTED: 'rose' }

export default function Visitors() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})

  const residents = useApi(
    () => residentApi.list({ status: 'live', branch_id: activeBranchId, page_size: 200 }),
    [activeBranchId], { enabled: can('customers.view') })
  const visitors = useApi(
    () => visitorApi.list({ search, status, branch_id: activeBranchId, page, page_size: 25 }),
    [search, status, activeBranchId, page])

  const rows = visitors.data?.items || []
  const pagination = visitors.data?.pagination

  const act = async (fn, message) => {
    try { await fn(); success(message); visitors.reload() }
    catch (err) { error('That did not work', err.message) }
  }

  const save = async () => {
    if (!f.resident_id) return error('Who are they visiting?')
    if (!f.name?.trim()) return error('Enter the visitor\u2019s name.')
    setBusy(true)
    try {
      await visitorApi.create({
        resident_id: f.resident_id, name: f.name.trim(), phone: f.phone || null,
        relation: f.relation || null, purpose: f.purpose || null,
        expected_at: f.expected_at ? new Date(f.expected_at).toISOString() : null,
        id_proof_reference: f.id_proof_reference || null })
      success('Visitor logged')
      setOpen(false); setF({})
      visitors.reload()
    } catch (err) { error('Could not log the visitor', err.message) }
    finally { setBusy(false) }
  }

  const columns = [
    { key: 'name', header: 'Visitor',
      render: (v) => <div><p className="font-medium text-slate-900">{v.name}</p>
        <p className="text-xs text-slate-500">{v.relation || 'Visitor'}{v.phone ? ` · ${v.phone}` : ''}</p></div> },
    { key: 'resident', header: 'Visiting', sortable: false,
      render: (v) => <span className="text-sm text-slate-700">{v.resident}</span> },
    { key: 'purpose', header: 'Purpose', sortable: false,
      render: (v) => <span className="text-sm text-slate-600 truncate">{v.purpose || '—'}</span> },
    { key: 'entry_at', header: 'Timing',
      render: (v) => <span className="text-xs text-slate-500 tnum">
        {v.entry_at ? `In ${dateTimeFmt(v.entry_at)}`
          : v.expected_at ? `Expected ${dateTimeFmt(v.expected_at)}` : relative(v.created_at)}
      </span> },
    { key: 'status', header: 'Status',
      render: (v) => <StatusBadge status={v.status} tone={TONE[v.status]} dot /> },
    { key: 'actions', header: '', sortable: false, align: 'right',
      render: (v) => (
        <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          {v.status === 'PENDING' && (
            <PermissionGuard perm="visitors.approve">
              <IconButton icon={Check} label="Approve"
                onClick={() => act(() => visitorApi.decide(v.id, true), `${v.name} approved`)} />
              <IconButton icon={X} label="Reject" tone="danger"
                onClick={() => act(() => visitorApi.decide(v.id, false), `${v.name} rejected`)} />
            </PermissionGuard>
          )}
          {v.status === 'APPROVED' && (
            <PermissionGuard perm="visitors.manage">
              <Button size="sm" icon={LogIn}
                onClick={() => act(() => visitorApi.entry(v.id), 'Entry recorded')}>In</Button>
            </PermissionGuard>
          )}
          {v.status === 'INSIDE' && (
            <PermissionGuard perm="visitors.manage">
              <Button size="sm" icon={LogOut}
                onClick={() => act(() => visitorApi.exit(v.id), 'Exit recorded')}>Out</Button>
            </PermissionGuard>
          )}
        </div>
      ) },
  ]

  return (
    <>
      <PageHeader title="Visitors" subtitle="Who is coming, who approved it and who is inside."
        actions={<PermissionGuard perm={['visitors.create', 'visitors.manage']}>
          <Button variant="primary" icon={Plus} onClick={() => { setF({}); setOpen(true) }}>
            Log a visitor</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Awaiting approval"
          value={num(rows.filter((v) => v.status === 'PENDING').length)}
          icon={UserPlus} tone="amber" />
        <StatCard label="Inside now"
          value={num(rows.filter((v) => v.status === 'INSIDE').length)} tone="brand" />
        <StatCard label="Approved today"
          value={num(rows.filter((v) => v.status === 'APPROVED').length)} tone="emerald" />
        <StatCard label="Completed"
          value={num(rows.filter((v) => v.status === 'COMPLETED').length)} tone="slate" />
      </div>

      <InlineAlert tone="info" className="mb-4">
        Entry is refused until a visitor is approved. That gate is enforced by the API,
        not by hiding the button.
      </InlineAlert>

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={(v) => { setSearch(v); setPage(1) }}
            searchPlaceholder="Search visitor name…"
            filters={[{ key: 'status', label: 'Status', value: status,
              onChange: (v) => { setStatus(v); setPage(1) }, options: STATUSES }]} />
        </div>

        {visitors.error ? (
          <InlineAlert tone="error" className="m-4">{visitors.error.message}</InlineAlert>
        ) : visitors.loading && !visitors.data ? (
          <div className="p-4 space-y-2">{[0, 1, 2].map((i) =>
            <Skeleton key={i} className="h-14" />)}</div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={25}
            mobileCard={(v) => (
              <div className="space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">{v.name}</p>
                    <p className="text-xs text-slate-500 truncate">
                      Visiting {v.resident}</p>
                  </div>
                  <StatusBadge status={v.status} tone={TONE[v.status]} />
                </div>
              </div>
            )}
            empty={<EmptyState icon={UserPlus} title="No visitors match"
              message="Log a visitor when someone arrives at the gate." />} />
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between">
            <p className="text-xs text-slate-500 tnum">
              Page {pagination.page} of {pagination.total_pages} · {pagination.total} visitors
            </p>
            <div className="flex gap-2">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" disabled={page >= pagination.total_pages}
                onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} size="sm" title="Log a visitor"
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>Log visitor</Button></>}>
        <div className="space-y-4">
          <FormField label="Visiting" required>
            <Select value={f.resident_id || ''}
              onChange={(e) => setF({ ...f, resident_id: e.target.value })}>
              <option value="">Choose a resident…</option>
              {(residents.data?.items || []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.full_name}{r.placement?.room ? ` — room ${r.placement.room}` : ''}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Visitor name" required>
            <Input value={f.name || ''} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Phone">
              <Input value={f.phone || ''} onChange={(e) => setF({ ...f, phone: e.target.value })} />
            </FormField>
            <FormField label="Relation">
              <Input value={f.relation || ''} placeholder="Father"
                onChange={(e) => setF({ ...f, relation: e.target.value })} />
            </FormField>
          </div>
          <FormField label="Purpose">
            <Input value={f.purpose || ''} onChange={(e) => setF({ ...f, purpose: e.target.value })} />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Expected at">
              <Input type="datetime-local" value={f.expected_at || ''}
                onChange={(e) => setF({ ...f, expected_at: e.target.value })} />
            </FormField>
            <FormField label="ID proof reference">
              <Input value={f.id_proof_reference || ''}
                onChange={(e) => setF({ ...f, id_proof_reference: e.target.value })} />
            </FormField>
          </div>
        </div>
      </Modal>
    </>
  )
}
