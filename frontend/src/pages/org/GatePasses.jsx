import { useState } from 'react'
import { Plus, DoorOpen, Check, X, LogOut, LogIn } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { gatePassApi } from '@/services/api/gatePassApi'
import { residentApi } from '@/services/api/residentApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard, Modal,
  FormField, Input, Select, Checkbox, InlineAlert, Skeleton, IconButton,
} from '@/components/ui'
import { num, dateTimeFmt } from '@/lib/format'

const STATUSES = ['PENDING', 'APPROVED', 'ACTIVE', 'COMPLETED', 'REJECTED', 'CANCELLED']
const TONE = { PENDING: 'amber', APPROVED: 'emerald', ACTIVE: 'brand',
  COMPLETED: 'slate', REJECTED: 'rose', CANCELLED: 'slate' }

export default function GatePasses() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})

  const residents = useApi(
    () => residentApi.list({ status: 'live', branch_id: activeBranchId, page_size: 200 }),
    [activeBranchId], { enabled: can('customers.view') })
  const passes = useApi(
    () => gatePassApi.list({ status, branch_id: activeBranchId, page, page_size: 25 }),
    [status, activeBranchId, page])

  const rows = passes.data?.items || []
  const pagination = passes.data?.pagination

  const act = async (fn, message) => {
    try { await fn(); success(message); passes.reload() }
    catch (err) { error('That did not work', err.message) }
  }

  const save = async () => {
    if (!f.resident_id) return error('Choose a resident.')
    if (!f.reason?.trim()) return error('Give a reason.')
    if (!f.from_at || !f.to_at) return error('Set both times.')
    setBusy(true)
    try {
      await gatePassApi.create({
        resident_id: f.resident_id, reason: f.reason.trim(),
        destination: f.destination || null,
        from_at: new Date(f.from_at).toISOString(),
        to_at: new Date(f.to_at).toISOString(),
        is_emergency: !!f.is_emergency })
      success('Gate pass raised')
      setOpen(false); setF({})
      passes.reload()
    } catch (err) { error('Could not raise it', err.message) }
    finally { setBusy(false) }
  }

  const columns = [
    { key: 'pass_number', header: 'Pass',
      render: (p) => <div><p className="font-medium text-slate-900">{p.pass_number}</p>
        <p className="text-xs text-slate-500 truncate">{p.resident}</p></div> },
    { key: 'reason', header: 'Reason', sortable: false,
      render: (p) => <div><p className="text-sm text-slate-800 truncate">{p.reason}</p>
        <p className="text-2xs text-slate-500">{p.destination || '—'}</p></div> },
    { key: 'from_at', header: 'Window',
      render: (p) => <div className="text-xs text-slate-600 tnum">
        <p>{dateTimeFmt(p.from_at)}</p><p className="text-slate-400">→ {dateTimeFmt(p.to_at)}</p></div> },
    { key: 'status', header: 'Status',
      render: (p) => (
        <div className="flex items-center gap-1.5">
          <StatusBadge status={p.status} tone={TONE[p.status]} dot />
          {p.is_emergency && <StatusBadge status="Emergency" tone="rose" />}
        </div>
      ) },
    { key: 'actions', header: '', sortable: false, align: 'right',
      render: (p) => (
        <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          {p.status === 'PENDING' && (
            <PermissionGuard perm="gatepass.approve">
              <IconButton icon={Check} label="Approve"
                onClick={() => act(() => gatePassApi.decide(p.id, true), 'Pass approved')} />
              <IconButton icon={X} label="Reject" tone="danger"
                onClick={() => act(() => gatePassApi.decide(p.id, false), 'Pass rejected')} />
            </PermissionGuard>
          )}
          {p.status === 'APPROVED' && (
            <PermissionGuard perm="gatepass.manage">
              <Button size="sm" icon={LogOut}
                onClick={() => act(() => gatePassApi.setStatus(p.id, 'ACTIVE'),
                  'Departure recorded')}>Left</Button>
            </PermissionGuard>
          )}
          {p.status === 'ACTIVE' && (
            <PermissionGuard perm="gatepass.manage">
              <Button size="sm" icon={LogIn}
                onClick={() => act(() => gatePassApi.setStatus(p.id, 'COMPLETED'),
                  'Return recorded')}>Back</Button>
            </PermissionGuard>
          )}
        </div>
      ) },
  ]

  return (
    <>
      <PageHeader title="Gate passes" subtitle="Leave requests, approvals and who is currently away."
        actions={<PermissionGuard perm={['gatepass.create', 'gatepass.manage']}>
          <Button variant="primary" icon={Plus} onClick={() => { setF({}); setOpen(true) }}>
            Raise a pass</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Awaiting approval"
          value={num(rows.filter((p) => p.status === 'PENDING').length)}
          icon={DoorOpen} tone="amber" />
        <StatCard label="Approved"
          value={num(rows.filter((p) => p.status === 'APPROVED').length)} tone="emerald" />
        <StatCard label="Currently away"
          value={num(rows.filter((p) => p.status === 'ACTIVE').length)} tone="brand" />
        <StatCard label="Emergency"
          value={num(rows.filter((p) => p.is_emergency).length)} tone="rose" />
      </div>

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar filters={[{ key: 'status', label: 'Status', value: status,
            onChange: (v) => { setStatus(v); setPage(1) }, options: STATUSES }]} />
        </div>

        {passes.error ? (
          <InlineAlert tone="error" className="m-4">{passes.error.message}</InlineAlert>
        ) : passes.loading && !passes.data ? (
          <div className="p-4 space-y-2">{[0, 1, 2].map((i) =>
            <Skeleton key={i} className="h-14" />)}</div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={25}
            mobileCard={(p) => (
              <div className="space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">{p.reason}</p>
                    <p className="text-xs text-slate-500 truncate">
                      {p.resident} · {p.pass_number}</p>
                  </div>
                  <StatusBadge status={p.status} tone={TONE[p.status]} />
                </div>
                <p className="text-2xs text-slate-400 tnum">
                  {dateTimeFmt(p.from_at)} → {dateTimeFmt(p.to_at)}</p>
              </div>
            )}
            empty={<EmptyState icon={DoorOpen} title="No gate passes"
              message="Residents raise these from their portal; you can also add one here." />} />
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} size="sm" title="Raise a gate pass"
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>Raise pass</Button></>}>
        <div className="space-y-4">
          <FormField label="Resident" required>
            <Select value={f.resident_id || ''}
              onChange={(e) => setF({ ...f, resident_id: e.target.value })}>
              <option value="">Choose…</option>
              {(residents.data?.items || []).map((r) => (
                <option key={r.id} value={r.id}>{r.full_name}</option>
              ))}
            </Select>
          </FormField>
          <FormField label="Reason" required>
            <Input value={f.reason || ''} placeholder="Home visit"
              onChange={(e) => setF({ ...f, reason: e.target.value })} />
          </FormField>
          <FormField label="Destination">
            <Input value={f.destination || ''}
              onChange={(e) => setF({ ...f, destination: e.target.value })} />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Leaving" required>
              <Input type="datetime-local" value={f.from_at || ''}
                onChange={(e) => setF({ ...f, from_at: e.target.value })} />
            </FormField>
            <FormField label="Returning" required>
              <Input type="datetime-local" value={f.to_at || ''}
                onChange={(e) => setF({ ...f, to_at: e.target.value })} />
            </FormField>
          </div>
          <Checkbox checked={!!f.is_emergency}
            onChange={(e) => setF({ ...f, is_emergency: e.target.checked })}
            label="Emergency" description="Flags the request for immediate attention." />
        </div>
      </Modal>
    </>
  )
}
