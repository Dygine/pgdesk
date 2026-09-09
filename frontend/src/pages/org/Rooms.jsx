import { useMemo, useState } from 'react'
import { Plus, DoorOpen, LayoutGrid, List, Pencil, Trash2 } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { roomApi, floorApi, buildingApi } from '@/services/api/propertyApi'
import { branchApi } from '@/services/api/branchApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, Modal, FormField, Input, Select, Checkbox, DataTable, StatusBadge,
  FilterBar, EmptyState, StatCard, IconButton, InlineAlert, Skeleton, ConfirmDialog,
  ProgressBar, Textarea,
} from '@/components/ui'
import { inr, num } from '@/lib/format'

const ROOM_TYPES = ['Single', 'Double', 'Triple', 'Four Sharing', 'Five Sharing', 'Dormitory']

const BED_TONE = {
  OCCUPIED: 'brand', AVAILABLE: 'emerald', RESERVED: 'amber',
  MAINTENANCE: 'rose', BLOCKED: 'slate',
}

export default function Rooms() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()

  const [view, setView] = useState('grid')
  const [search, setSearch] = useState('')
  const [floorId, setFloorId] = useState('all')
  const [roomType, setRoomType] = useState('all')
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})
  const [errs, setErrs] = useState({})

  const branches = useApi(() => branchApi.list(), [], { enabled: can('branches.view') })
  const buildings = useApi(() => buildingApi.list({ branch_id: activeBranchId }), [activeBranchId])
  const floors = useApi(() => floorApi.list({ branch_id: activeBranchId }), [activeBranchId])
  const plan = useApi(() => subscriptionApi.mine(), [], { enabled: can('dashboard.view') })
  const rooms = useApi(
    () => roomApi.list({
      branch_id: activeBranchId, floor_id: floorId, room_type: roomType,
      status, search, page, page_size: 60,
    }),
    [activeBranchId, floorId, roomType, status, search, page],
  )

  const rows = rooms.data?.items || []
  const pagination = rooms.data?.pagination
  const floorRows = floors.data || []
  const buildingRows = buildings.data || []
  const branchRows = branches.data?.items || []

  const floorLabel = (id) => {
    const fl = floorRows.find((x) => x.id === id)
    if (!fl) return ''
    const b = buildingRows.find((x) => x.id === fl.building_id)
    return `${b?.name || ''} · ${fl.name}`
  }

  const totals = useMemo(() => rows.reduce((a, r) => ({
    beds: a.beds + (r.occupancy?.total || 0),
    occupied: a.occupied + (r.occupancy?.occupied || 0),
    available: a.available + (r.occupancy?.available || 0),
  }), { beds: 0, occupied: 0, available: 0 }), [rows])

  const roomLimit = plan.data?.limits?.rooms
  const roomsUsed = plan.data?.usage?.rooms ?? 0

  const openNew = () => {
    setF({ floor_id: floorRows[0]?.id || '', room_number: '', room_type: 'Double',
      capacity: 2, rent_amount: '', deposit_amount: '', has_ac: false,
      has_attached_bathroom: true, description: '', generate_beds: true })
    setErrs({}); setModal('new')
  }
  const openEdit = (r) => {
    setF({ ...r, rent_amount: String(r.rent_amount), deposit_amount: String(r.deposit_amount) })
    setErrs({}); setModal(r)
  }
  const set = (k) => (v) => {
    const val = v?.target ? (v.target.type === 'checkbox' ? v.target.checked : v.target.value) : v
    setF((x) => ({ ...x, [k]: val }))
    setErrs((x) => ({ ...x, [k]: undefined }))
  }

  const save = async () => {
    const e = {}
    if (!String(f.room_number).trim()) e.room_number = 'Room number is required.'
    if (modal === 'new' && !f.floor_id) e.floor_id = 'Choose a floor.'
    if (!Number(f.rent_amount)) e.rent_amount = 'Enter the monthly rent.'
    setErrs(e)
    if (Object.keys(e).length) return

    setBusy(true)
    try {
      if (modal === 'new') {
        await roomApi.create({
          floor_id: f.floor_id, room_number: String(f.room_number).trim(),
          room_type: f.room_type, capacity: Number(f.capacity) || 1,
          rent_amount: Number(f.rent_amount),
          deposit_amount: Number(f.deposit_amount) || undefined,
          has_ac: !!f.has_ac, has_attached_bathroom: !!f.has_attached_bathroom,
          description: f.description, generate_beds: !!f.generate_beds,
        })
        success(`Room ${f.room_number} created`,
          f.generate_beds ? `${f.capacity} beds added automatically.` : undefined)
      } else {
        await roomApi.update(modal.id, {
          room_number: String(f.room_number).trim(), room_type: f.room_type,
          rent_amount: Number(f.rent_amount), deposit_amount: Number(f.deposit_amount),
          has_ac: !!f.has_ac, has_attached_bathroom: !!f.has_attached_bathroom,
          description: f.description, status: f.status,
        })
        success(`Room ${f.room_number} updated`)
      }
      setModal(null)
      rooms.reload(); plan.reload()
    } catch (err) {
      error(modal === 'new' ? 'Could not create the room' : 'Could not save', err.message)
    } finally { setBusy(false) }
  }

  const remove = async () => {
    try {
      await roomApi.remove(confirm.id)
      success('Room deleted')
      rooms.reload(); plan.reload()
    } catch (err) { error('Could not delete', err.message) } finally { setConfirm(null) }
  }

  const columns = [
    { key: 'room_number', header: 'Room',
      render: (r) => <div><p className="font-medium text-slate-900">Room {r.room_number}</p>
        <p className="text-xs text-slate-500 truncate">{floorLabel(r.floor_id)}</p></div> },
    { key: 'room_type', header: 'Type',
      render: (r) => <span className="text-slate-700">{r.room_type}</span> },
    { key: 'occupancy', header: 'Beds', align: 'right', sortable: false,
      render: (r) => (
        <div className="min-w-[92px]">
          <p className="tnum text-sm text-slate-800">
            {r.occupancy?.occupied ?? 0}/{r.occupancy?.total ?? 0}</p>
          <ProgressBar value={r.occupancy?.occupied ?? 0} max={r.occupancy?.total || 1}
            className="mt-1" />
        </div>
      ) },
    { key: 'rent_amount', header: 'Rent', align: 'right',
      render: (r) => <span className="tnum font-medium text-slate-900">{inr(r.rent_amount)}</span> },
    { key: 'deposit_amount', header: 'Deposit', align: 'right', hideBelow: 'xl',
      render: (r) => <span className="tnum text-slate-600">{inr(r.deposit_amount)}</span> },
    { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} dot /> },
    { key: 'actions', header: '', sortable: false, align: 'right',
      render: (r) => (
        <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          <PermissionGuard perm="rooms.edit">
            <IconButton icon={Pencil} label="Edit room" onClick={() => openEdit(r)} />
          </PermissionGuard>
          <PermissionGuard perm="rooms.delete">
            <IconButton icon={Trash2} label="Delete room" tone="danger"
              onClick={() => setConfirm(r)} />
          </PermissionGuard>
        </div>
      ) },
  ]

  return (
    <>
      <PageHeader title="Rooms"
        subtitle="Every room and what it earns. Beds are created from the capacity you set."
        actions={<PermissionGuard perm="rooms.create">
          <Button variant="primary" icon={Plus} onClick={openNew}
            disabled={!floorRows.length}>Add room</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Rooms" value={`${roomsUsed}${roomLimit ? ` / ${roomLimit}` : ''}`}
          icon={DoorOpen} tone="brand"
          footer={roomLimit ? <ProgressBar value={roomsUsed} max={roomLimit} /> : undefined} />
        <StatCard label="Beds in view" value={num(totals.beds)} tone="violet" />
        <StatCard label="Available" value={num(totals.available)} tone="emerald" />
        <StatCard label="Occupancy"
          value={totals.beds ? `${Math.round(totals.occupied / totals.beds * 100)}%` : '—'}
          tone="blue" />
      </div>

      {!floorRows.length && !floors.loading && (
        <InlineAlert tone="warn" className="mb-4" title="No floors yet">
          Rooms sit on a floor. Create a building and a floor first, from Buildings &amp; floors.
        </InlineAlert>
      )}

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={(v) => { setSearch(v); setPage(1) }}
            searchPlaceholder="Search room number…"
            filters={[
              { key: 'floor', label: 'Floor', value: floorId,
                onChange: (v) => { setFloorId(v); setPage(1) },
                options: floorRows.map((fl) => ({ value: fl.id, label: floorLabel(fl.id) })) },
              { key: 'type', label: 'Type', value: roomType,
                onChange: (v) => { setRoomType(v); setPage(1) }, options: ROOM_TYPES },
              { key: 'status', label: 'Status', value: status,
                onChange: (v) => { setStatus(v); setPage(1) },
                options: ['ACTIVE', 'INACTIVE', 'MAINTENANCE'] },
            ]}
            actions={
              <div className="flex rounded-lg border border-line overflow-hidden shrink-0">
                {[['grid', LayoutGrid], ['list', List]].map(([v, Icon]) => (
                  <button key={v} onClick={() => setView(v)} aria-label={`${v} view`}
                    className={`h-10 w-10 inline-flex items-center justify-center ${
                      view === v ? 'bg-brand-50 text-brand-800' : 'bg-white text-slate-400 hover:text-slate-700'}`}>
                    <Icon size={16} />
                  </button>
                ))}
              </div>
            } />
        </div>

        {rooms.error ? (
          <InlineAlert tone="error" className="m-4">{rooms.error.message}</InlineAlert>
        ) : rooms.loading && !rooms.data ? (
          <div className="p-4 grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-3">
            {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-32" />)}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState icon={DoorOpen} title="No rooms match"
            message="Clear the filters, or add a room — its beds are created for you." />
        ) : view === 'grid' ? (
          <div className="p-4 grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-3">
            {rows.map((r) => (
              <button key={r.id} onClick={() => openEdit(r)}
                className="rounded-lg border border-line p-3.5 text-left hover:shadow-lift transition-shadow">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-900">Room {r.room_number}</p>
                  {r.has_ac && <StatusBadge status="AC" tone="blue" />}
                </div>
                <p className="text-2xs text-slate-500 truncate">{r.room_type}</p>
                <div className="flex gap-1 mt-2 flex-wrap">
                  {r.beds.map((b) => (
                    <span key={b.id} title={`Bed ${b.bed_number}: ${b.status}`}
                      className={`h-6 w-6 rounded text-2xs font-medium inline-flex items-center justify-center ${
                        { OCCUPIED: 'bg-brand-100 text-brand-800',
                          AVAILABLE: 'bg-emerald-50 text-emerald-700',
                          RESERVED: 'bg-amber-50 text-amber-700',
                          MAINTENANCE: 'bg-rose-50 text-rose-700',
                          BLOCKED: 'bg-slate-100 text-slate-500' }[b.status]}`}>
                      {b.bed_number}
                    </span>
                  ))}
                </div>
                <p className="text-sm font-medium text-slate-900 tnum mt-2">{inr(r.rent_amount)}</p>
                <p className="text-2xs text-slate-500 tnum">
                  {r.occupancy?.occupied}/{r.occupancy?.total} occupied
                </p>
              </button>
            ))}
          </div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={60}
            mobileCard={(r) => (
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900">Room {r.room_number}</p>
                  <p className="text-xs text-slate-500 truncate">
                    {r.room_type} · {r.occupancy?.occupied}/{r.occupancy?.total} beds
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-sm font-semibold text-slate-900 tnum">{inr(r.rent_amount)}</p>
                  <StatusBadge status={r.status} />
                </div>
              </div>
            )} />
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between">
            <p className="text-xs text-slate-500 tnum">
              Page {pagination.page} of {pagination.total_pages} · {pagination.total} rooms
            </p>
            <div className="flex gap-2">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" disabled={page >= pagination.total_pages}
                onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      <Modal open={!!modal} onClose={() => setModal(null)} size="md"
        title={modal === 'new' ? 'Add a room' : `Edit room ${f.room_number}`}
        subtitle={modal === 'new' ? 'Beds are created from the capacity.' : undefined}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>
            {modal === 'new' ? 'Create room' : 'Save changes'}</Button></>}>
        <div className="space-y-5">
          <div className="grid sm:grid-cols-2 gap-4">
            {modal === 'new' && (
              <FormField label="Floor" required error={errs.floor_id} className="sm:col-span-2">
                <Select value={f.floor_id || ''} onChange={set('floor_id')} error={errs.floor_id}>
                  <option value="">Choose a floor…</option>
                  {floorRows.map((fl) => (
                    <option key={fl.id} value={fl.id}>{floorLabel(fl.id)}</option>
                  ))}
                </Select>
              </FormField>
            )}
            <FormField label="Room number" required error={errs.room_number}>
              <Input value={f.room_number ?? ''} onChange={set('room_number')}
                error={errs.room_number} placeholder="204" />
            </FormField>
            <FormField label="Room type">
              <Select value={f.room_type || 'Double'} onChange={set('room_type')}>
                {ROOM_TYPES.map((x) => <option key={x}>{x}</option>)}
              </Select>
            </FormField>
            {modal === 'new' && (
              <FormField label="Capacity" required hint="One bed is created per unit.">
                <Input inputMode="numeric" className="tnum" value={f.capacity ?? 1}
                  onChange={set('capacity')} />
              </FormField>
            )}
            <FormField label="Monthly rent" required error={errs.rent_amount}>
              <Input inputMode="numeric" className="tnum" value={f.rent_amount ?? ''}
                onChange={set('rent_amount')} error={errs.rent_amount} placeholder="9000" />
            </FormField>
            <FormField label="Deposit" hint="Defaults to two months.">
              <Input inputMode="numeric" className="tnum" value={f.deposit_amount ?? ''}
                onChange={set('deposit_amount')} />
            </FormField>
            {modal !== 'new' && (
              <FormField label="Status">
                <Select value={f.status || 'ACTIVE'} onChange={set('status')}>
                  {['ACTIVE', 'INACTIVE', 'MAINTENANCE'].map((x) => <option key={x}>{x}</option>)}
                </Select>
              </FormField>
            )}
            <FormField label="Description" className="sm:col-span-2">
              <Textarea rows={2} value={f.description || ''} onChange={set('description')} />
            </FormField>
          </div>

          <div className="space-y-2.5">
            <Checkbox checked={!!f.has_ac} onChange={set('has_ac')} label="Air conditioned" />
            <Checkbox checked={!!f.has_attached_bathroom} onChange={set('has_attached_bathroom')}
              label="Attached bathroom" />
            {modal === 'new' && (
              <Checkbox checked={!!f.generate_beds} onChange={set('generate_beds')}
                label="Create the beds automatically"
                description="One bed per unit of capacity, labelled A, B, C…" />
            )}
          </div>
        </div>
      </Modal>

      <ConfirmDialog open={!!confirm} onClose={() => setConfirm(null)} tone="danger"
        title={`Delete room ${confirm?.room_number}?`} confirmLabel="Delete room"
        message="Its beds go with it. Refused if any bed still has a resident."
        onConfirm={remove} />
    </>
  )
}
