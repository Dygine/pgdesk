import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BedDouble, Plus, Wrench, Ban, CircleCheck, Trash2 } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { bedApi, roomApi } from '@/services/api/propertyApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard, Modal,
  FormField, Input, Select, IconButton, InlineAlert, Skeleton, ConfirmDialog, ProgressBar,
} from '@/components/ui'
import { inr, num } from '@/lib/format'

const STATUSES = ['AVAILABLE', 'RESERVED', 'OCCUPIED', 'MAINTENANCE', 'BLOCKED']

export default function Beds() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()

  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [roomId, setRoomId] = useState('all')
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})

  const plan = useApi(() => subscriptionApi.mine(), [], { enabled: can('dashboard.view') })
  const rooms = useApi(
    () => roomApi.list({ branch_id: activeBranchId, page_size: 200 }), [activeBranchId])
  const beds = useApi(
    () => bedApi.list({ branch_id: activeBranchId, room_id: roomId, status, search,
      page, page_size: 100 }),
    [activeBranchId, roomId, status, search, page],
  )

  const rows = beds.data?.items || []
  const pagination = beds.data?.pagination
  const roomRows = rooms.data?.items || []
  const roomById = useMemo(
    () => Object.fromEntries(roomRows.map((r) => [r.id, r])), [roomRows])

  const counts = useMemo(() => {
    const c = Object.fromEntries(STATUSES.map((s) => [s, 0]))
    rows.forEach((b) => { c[b.status] = (c[b.status] || 0) + 1 })
    return c
  }, [rows])

  const bedLimit = plan.data?.limits?.beds
  const bedsUsed = plan.data?.usage?.beds ?? 0

  const changeStatus = async (bed, next) => {
    try {
      await bedApi.setStatus(bed.id, next)
      success(`Bed ${bed.bed_number} is now ${next.toLowerCase()}`)
      beds.reload()
    } catch (err) {
      error('Could not change the status', err.message)
    }
  }

  const openNew = () => {
    setF({ room_id: roomRows[0]?.id || '', bed_number: '', rent_amount: '', notes: '' })
    setModal('new')
  }

  const save = async () => {
    if (!f.room_id || !String(f.bed_number).trim()) {
      return error('A room and a bed number are both required.')
    }
    setBusy(true)
    try {
      await bedApi.create({
        room_id: f.room_id, bed_number: String(f.bed_number).trim().toUpperCase(),
        rent_amount: Number(f.rent_amount) || undefined, notes: f.notes || undefined,
      })
      success(`Bed ${f.bed_number} created`)
      setModal(null)
      beds.reload(); plan.reload()
    } catch (err) {
      error('Could not create the bed', err.message)
    } finally { setBusy(false) }
  }

  const remove = async () => {
    try {
      await bedApi.remove(confirm.id)
      success('Bed deleted')
      beds.reload(); plan.reload()
    } catch (err) { error('Could not delete', err.message) } finally { setConfirm(null) }
  }

  const columns = [
    { key: 'bed_code', header: 'Bed',
      render: (b) => <div><p className="font-medium text-slate-900">{b.bed_code || b.bed_number}</p>
        <p className="text-xs text-slate-500">
          Room {roomById[b.room_id]?.room_number || '—'} · bed {b.bed_number}</p></div> },
    { key: 'room', header: 'Room type', sortable: false,
      render: (b) => <span className="text-slate-700">
        {roomById[b.room_id]?.room_type || '—'}</span> },
    { key: 'rent_amount', header: 'Rent', align: 'right',
      render: (b) => <span className="tnum font-medium text-slate-900">{inr(b.rent_amount)}</span> },
    { key: 'status', header: 'Status', render: (b) => <StatusBadge status={b.status} dot /> },
    { key: 'actions', header: '', sortable: false, align: 'right',
      render: (b) => (
        <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          {b.status !== 'OCCUPIED' && (
            <PermissionGuard perm={['beds.edit', 'beds.block']}>
              {b.status !== 'AVAILABLE' && (
                <IconButton icon={CircleCheck} label="Mark available"
                  onClick={() => changeStatus(b, 'AVAILABLE')} />
              )}
              {b.status !== 'MAINTENANCE' && (
                <IconButton icon={Wrench} label="Mark for maintenance"
                  onClick={() => changeStatus(b, 'MAINTENANCE')} />
              )}
              {b.status !== 'BLOCKED' && (
                <IconButton icon={Ban} label="Block bed"
                  onClick={() => changeStatus(b, 'BLOCKED')} />
              )}
            </PermissionGuard>
          )}
          {b.status !== 'OCCUPIED' && (
            <PermissionGuard perm="beds.delete">
              <IconButton icon={Trash2} label="Delete bed" tone="danger"
                onClick={() => setConfirm(b)} />
            </PermissionGuard>
          )}
        </div>
      ) },
  ]

  return (
    <>
      <PageHeader title="Beds"
        subtitle="Bed-level inventory — the unit you actually sell."
        actions={<PermissionGuard perm="beds.create">
          <Button variant="primary" icon={Plus} onClick={openNew}
            disabled={!roomRows.length}>Add bed</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 sm:gap-4 mb-4">
        <StatCard label="Beds" value={`${bedsUsed}${bedLimit ? ` / ${bedLimit}` : ''}`}
          icon={BedDouble} tone="brand"
          footer={bedLimit ? <ProgressBar value={bedsUsed} max={bedLimit} /> : undefined} />
        <StatCard label="Occupied" value={num(counts.OCCUPIED)} tone="violet" />
        <StatCard label="Available" value={num(counts.AVAILABLE)} tone="emerald" />
        <StatCard label="Reserved" value={num(counts.RESERVED)} tone="amber" />
        <StatCard label="Out of service"
          value={num(counts.MAINTENANCE + counts.BLOCKED)} tone="rose" />
      </div>

      <InlineAlert tone="info" className="mb-4">
        A bed becomes occupied by <Link to="/app/check-in" className="underline font-medium">
        checking a resident in</Link>, which assigns the bed, records the terms and raises
        the first invoice together. The API refuses a direct change to OCCUPIED, and the
        database will not store an occupied bed with nobody in it.
      </InlineAlert>

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={(v) => { setSearch(v); setPage(1) }}
            searchPlaceholder="Search bed code…"
            filters={[
              { key: 'room', label: 'Room', value: roomId,
                onChange: (v) => { setRoomId(v); setPage(1) },
                options: roomRows.map((r) => ({ value: r.id, label: `Room ${r.room_number}` })) },
              { key: 'status', label: 'Status', value: status,
                onChange: (v) => { setStatus(v); setPage(1) }, options: STATUSES },
            ]} />
        </div>

        {beds.error ? (
          <InlineAlert tone="error" className="m-4">{beds.error.message}</InlineAlert>
        ) : beds.loading && !beds.data ? (
          <div className="p-4 space-y-2">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}
          </div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={100}
            mobileCard={(b) => (
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900 truncate">
                    {b.bed_code || b.bed_number}</p>
                  <p className="text-xs text-slate-500">
                    Room {roomById[b.room_id]?.room_number || '—'} · {inr(b.rent_amount)}</p>
                </div>
                <StatusBadge status={b.status} />
              </div>
            )}
            empty={<EmptyState icon={BedDouble} title="No beds match"
              message="Clear the filters, or create a room — its beds are generated with it." />} />
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between">
            <p className="text-xs text-slate-500 tnum">
              Page {pagination.page} of {pagination.total_pages} · {pagination.total} beds
            </p>
            <div className="flex gap-2">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" disabled={page >= pagination.total_pages}
                onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      <Modal open={!!modal} onClose={() => setModal(null)} size="sm" title="Add a bed"
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>Create bed</Button></>}>
        <div className="space-y-4">
          <FormField label="Room" required>
            <Select value={f.room_id || ''} onChange={(e) => setF({ ...f, room_id: e.target.value })}>
              <option value="">Choose a room…</option>
              {roomRows.map((r) => (
                <option key={r.id} value={r.id}>
                  Room {r.room_number} — {r.room_type} ({r.occupancy?.total ?? 0} beds)
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Bed number" required hint="A single letter or short label: A, B, C…">
            <Input value={f.bed_number ?? ''} className="uppercase"
              onChange={(e) => setF({ ...f, bed_number: e.target.value })} placeholder="C" />
          </FormField>
          <FormField label="Rent" hint="Defaults to the room's rent.">
            <Input inputMode="numeric" className="tnum" value={f.rent_amount ?? ''}
              onChange={(e) => setF({ ...f, rent_amount: e.target.value })} />
          </FormField>
          <FormField label="Notes">
            <Input value={f.notes ?? ''} onChange={(e) => setF({ ...f, notes: e.target.value })} />
          </FormField>
        </div>
      </Modal>

      <ConfirmDialog open={!!confirm} onClose={() => setConfirm(null)} tone="danger"
        title={`Delete bed ${confirm?.bed_code || confirm?.bed_number}?`} confirmLabel="Delete bed"
        message="This reduces the room's capacity. Refused if the bed has a resident."
        onConfirm={remove} />
    </>
  )
}
