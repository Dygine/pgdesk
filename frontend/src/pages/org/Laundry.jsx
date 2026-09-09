import { useState } from 'react'
import { Shirt, Plus, Calendar } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { laundryApi } from '@/services/api/laundryApi'
import { branchApi } from '@/services/api/branchApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, Button, DataTable, StatusBadge, FilterBar, EmptyState,
  StatCard, Modal, FormField, Input, Select, InlineAlert, Skeleton, ProgressBar,
} from '@/components/ui'
import { num, dateFmt, timeOnly, today } from '@/lib/format'

const FLOW = ['BOOKED', 'RECEIVED', 'PROCESSING', 'READY', 'COLLECTED']
const TONE = { BOOKED: 'brand', RECEIVED: 'amber', PROCESSING: 'amber',
  READY: 'emerald', COLLECTED: 'slate', CANCELLED: 'slate' }

export default function Laundry() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [status, setStatus] = useState('all')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})

  const branches = useApi(() => branchApi.list(), [], { enabled: can('branches.view') })
  const slots = useApi(() => laundryApi.slots({ branch_id: activeBranchId, from_date: today() }),
    [activeBranchId])
  const requests = useApi(
    () => laundryApi.requests({ status, branch_id: activeBranchId, page_size: 100 }),
    [status, activeBranchId])

  const rows = requests.data?.items || []
  const slotRows = slots.data || []

  const advance = async (r) => {
    const next = FLOW[Math.min(FLOW.indexOf(r.status) + 1, FLOW.length - 1)]
    try {
      await laundryApi.setStatus(r.id, next)
      success(`Marked ${next.toLowerCase()}`)
      requests.reload()
    } catch (err) { error('Could not update', err.message) }
  }

  const createSlot = async () => {
    if (!f.branch_id || !f.on_date || !f.start_time || !f.end_time) {
      return error('Fill in the branch, date and times.')
    }
    setBusy(true)
    try {
      await laundryApi.createSlot({
        branch_id: f.branch_id, on_date: f.on_date,
        start_time: f.start_time, end_time: f.end_time,
        capacity: Number(f.capacity) || 10 })
      success('Slot created')
      setOpen(false)
      slots.reload()
    } catch (err) { error('Could not create the slot', err.message) }
    finally { setBusy(false) }
  }

  const columns = [
    { key: 'resident', header: 'Resident',
      render: (r) => <div><p className="font-medium text-slate-900">{r.resident}</p>
        <p className="text-xs text-slate-500 tnum">
          {r.slot ? `${dateFmt(r.slot.on_date)} · ${timeOnly(r.slot.start_time)}` : '—'}</p></div> },
    { key: 'item_count', header: 'Items', align: 'right',
      render: (r) => <span className="tnum text-slate-700">{r.item_count}</span> },
    { key: 'status', header: 'Status',
      render: (r) => <StatusBadge status={r.status} tone={TONE[r.status]} dot /> },
    { key: 'actions', header: '', sortable: false, align: 'right',
      render: (r) => (
        <div onClick={(e) => e.stopPropagation()}>
          {!['COLLECTED', 'CANCELLED'].includes(r.status) && (
            <PermissionGuard perm="laundry.manage">
              <Button size="sm" onClick={() => advance(r)}>
                Mark {FLOW[Math.min(FLOW.indexOf(r.status) + 1, FLOW.length - 1)].toLowerCase()}
              </Button>
            </PermissionGuard>
          )}
        </div>
      ) },
  ]

  return (
    <>
      <PageHeader title="Laundry" subtitle="Slots, bookings and what stage each load is at."
        actions={<PermissionGuard perm="laundry.manage">
          <Button variant="primary" icon={Plus}
            onClick={() => { setF({ branch_id: activeBranchId || '', on_date: today(),
              start_time: '08:00', end_time: '11:00', capacity: '8' }); setOpen(true) }}>
            Add a slot</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Active loads"
          value={num(rows.filter((r) => !['COLLECTED', 'CANCELLED'].includes(r.status)).length)}
          icon={Shirt} tone="brand" />
        <StatCard label="Ready to collect"
          value={num(rows.filter((r) => r.status === 'READY').length)} tone="emerald" />
        <StatCard label="Upcoming slots" value={num(slotRows.length)}
          icon={Calendar} tone="slate" />
        <StatCard label="Free places"
          value={num(slotRows.reduce((a, s) => a + s.remaining, 0))} tone="violet" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Slots" subtitle="From today onwards" />
          {slots.loading && !slots.data ? (
            <div className="p-4"><Skeleton className="h-40" /></div>
          ) : slotRows.length === 0 ? (
            <EmptyState icon={Calendar} compact title="No slots yet"
              message="Publish some so residents can book." />
          ) : (
            <div className="p-4 grid sm:grid-cols-2 gap-2.5 max-h-[520px] overflow-y-auto">
              {slotRows.map((s) => (
                <div key={s.id} className="rounded-lg border border-line p-3.5">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <p className="text-sm font-medium text-slate-900 tnum">
                      {dateFmt(s.on_date)}</p>
                    <StatusBadge status={s.status} tone={TONE[s.status] || 'slate'} />
                  </div>
                  <p className="text-xs text-slate-600 tnum">
                    {timeOnly(s.start_time)} – {timeOnly(s.end_time)}
                  </p>
                  <ProgressBar value={s.booked} max={s.capacity} className="mt-2"
                    tone={s.remaining <= 0 ? 'rose' : 'brand'} />
                  <p className="text-2xs text-slate-500 tnum mt-1">
                    {s.booked}/{s.capacity} booked
                  </p>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <div className="p-4 border-b border-line">
            <FilterBar filters={[{ key: 'status', label: 'Status', value: status,
              onChange: setStatus, options: [...FLOW, 'CANCELLED'] }]} />
          </div>
          {requests.error ? (
            <InlineAlert tone="error" className="m-4">{requests.error.message}</InlineAlert>
          ) : (
            <DataTable columns={columns} rows={rows} pageSize={50}
              mobileCard={(r) => (
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">{r.resident}</p>
                    <p className="text-xs text-slate-500 tnum">{r.item_count} items</p>
                  </div>
                  <StatusBadge status={r.status} tone={TONE[r.status]} />
                </div>
              )}
              empty={<EmptyState icon={Shirt} title="No bookings"
                message="Residents book slots from their own portal." />} />
          )}
        </Card>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} size="sm" title="Add a laundry slot"
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={createSlot}>Create slot</Button></>}>
        <div className="space-y-4">
          <FormField label="Branch" required>
            <Select value={f.branch_id || ''}
              onChange={(e) => setF({ ...f, branch_id: e.target.value })}>
              <option value="">Choose…</option>
              {(branches.data?.items || []).map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </Select>
          </FormField>
          <FormField label="Date" required>
            <Input type="date" value={f.on_date || ''}
              onChange={(e) => setF({ ...f, on_date: e.target.value })} />
          </FormField>
          <div className="grid grid-cols-3 gap-3">
            <FormField label="From" required>
              <Input type="time" value={f.start_time || ''}
                onChange={(e) => setF({ ...f, start_time: e.target.value })} />
            </FormField>
            <FormField label="To" required>
              <Input type="time" value={f.end_time || ''}
                onChange={(e) => setF({ ...f, end_time: e.target.value })} />
            </FormField>
            <FormField label="Capacity">
              <Input inputMode="numeric" className="tnum" value={f.capacity || ''}
                onChange={(e) => setF({ ...f, capacity: e.target.value })} />
            </FormField>
          </div>
          <InlineAlert tone="info">
            Bookings are capped at the capacity — the server locks the slot when
            someone books, so it cannot be oversold.
          </InlineAlert>
        </div>
      </Modal>
    </>
  )
}
