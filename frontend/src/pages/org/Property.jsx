import { useState } from 'react'
import { Plus, Building, Layers3, Trash2, Pencil } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { buildingApi, floorApi } from '@/services/api/propertyApi'
import { branchApi } from '@/services/api/branchApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, Button, StatCard, StatusBadge, EmptyState, Modal, FormField,
  Input, Select, Textarea, Skeleton, InlineAlert, ConfirmDialog, IconButton,
} from '@/components/ui'
import { num } from '@/lib/format'

export default function Property() {
  const { activeBranchId } = useAuth()
  const { success, error } = useToast()
  const [modal, setModal] = useState(null)     // { type, mode, data }
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})

  const branches = useApi(() => branchApi.list(), [])
  const buildings = useApi(() => buildingApi.list({ branch_id: activeBranchId }), [activeBranchId])
  const floors = useApi(() => floorApi.list({ branch_id: activeBranchId }), [activeBranchId])

  const branchRows = branches.data?.items || []
  const buildingRows = buildings.data || []
  const floorRows = floors.data || []

  const reload = () => { buildings.reload(); floors.reload() }

  const openBuilding = (branchId, existing) => {
    setF(existing
      ? { ...existing }
      : { branch_id: branchId, name: '', code: '', description: '', number_of_floors: 1 })
    setModal({ type: 'building', mode: existing ? 'edit' : 'new' })
  }
  const openFloor = (buildingId, existing) => {
    setF(existing ? { ...existing } : { building_id: buildingId, floor_number: '', name: '' })
    setModal({ type: 'floor', mode: existing ? 'edit' : 'new' })
  }
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))

  const save = async () => {
    setBusy(true)
    try {
      const { type, mode } = modal
      if (type === 'building') {
        if (mode === 'new') {
          await buildingApi.create({ ...f, number_of_floors: Number(f.number_of_floors) || 1 })
          success(`${f.name} created`)
        } else {
          await buildingApi.update(f.id, {
            name: f.name, description: f.description,
            number_of_floors: Number(f.number_of_floors) || 1, status: f.status })
          success(`${f.name} updated`)
        }
      } else {
        if (mode === 'new') {
          await floorApi.create({ ...f, floor_number: Number(f.floor_number) })
          success('Floor created')
        } else {
          await floorApi.update(f.id, { name: f.name, status: f.status })
          success('Floor updated')
        }
      }
      setModal(null)
      reload()
    } catch (err) {
      error('That did not work', err.message)
    } finally { setBusy(false) }
  }

  const remove = async () => {
    try {
      if (confirm.type === 'building') await buildingApi.remove(confirm.data.id)
      else await floorApi.remove(confirm.data.id)
      success('Deleted')
      reload()
    } catch (err) {
      error('Could not delete', err.message)
    } finally { setConfirm(null) }
  }

  const loading = branches.loading || buildings.loading || floors.loading

  return (
    <>
      <PageHeader title="Buildings & floors"
        subtitle="The physical structure under each branch. Rooms hang off a floor." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Branches" value={num(branchRows.length)} icon={Building} tone="brand" />
        <StatCard label="Buildings" value={num(buildingRows.length)} tone="violet" />
        <StatCard label="Floors" value={num(floorRows.length)} icon={Layers3} tone="blue" />
        <StatCard label="Rooms"
          value={num(floorRows.reduce((a, f2) => a + (f2.counts?.rooms || 0), 0))} tone="emerald" />
      </div>

      {loading && !buildings.data ? (
        <Skeleton className="h-64" />
      ) : branchRows.length === 0 ? (
        <Card><EmptyState icon={Building} title="No branches yet"
          message="Add a branch first — buildings sit underneath one." /></Card>
      ) : (
        <div className="space-y-4">
          {branchRows.map((branch) => {
            const mine = buildingRows.filter((b) => b.branch_id === branch.id)
            return (
              <Card key={branch.id}>
                <CardHeader title={branch.name}
                  subtitle={`${mine.length} building${mine.length === 1 ? '' : 's'} · ${branch.counts?.rooms || 0} rooms`}
                  action={<PermissionGuard perm={['buildings.create', 'property.create']}>
                    <Button size="sm" icon={Plus} onClick={() => openBuilding(branch.id)}>Building</Button>
                  </PermissionGuard>} />

                {mine.length === 0 ? (
                  <EmptyState icon={Building} compact title="No buildings in this branch"
                    message="Even a single-building PG needs one entry so floors have a parent."
                    action={<PermissionGuard perm={['buildings.create', 'property.create']}>
                      <Button variant="primary" size="sm" icon={Plus}
                        onClick={() => openBuilding(branch.id)}>Add building</Button>
                    </PermissionGuard>} />
                ) : (
                  <div className="divide-y divide-line">
                    {mine.map((building) => {
                      const bFloors = floorRows.filter((fl) => fl.building_id === building.id)
                      return (
                        <div key={building.id} className="p-4 sm:p-5">
                          <div className="flex items-center justify-between gap-3 mb-3">
                            <div className="flex items-center gap-2.5 min-w-0">
                              <span className="h-8 w-8 rounded-lg bg-brand-50 text-brand-700 inline-flex items-center justify-center shrink-0">
                                <Building size={16} />
                              </span>
                              <div className="min-w-0">
                                <p className="text-sm font-semibold text-slate-900 truncate">
                                  {building.name} <span className="text-slate-400">· {building.code}</span>
                                </p>
                                <p className="text-2xs text-slate-500">
                                  {bFloors.length} floor{bFloors.length === 1 ? '' : 's'}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0">
                              <PermissionGuard perm={['buildings.edit', 'property.edit']}>
                                <IconButton icon={Pencil} label="Edit building"
                                  onClick={() => openBuilding(branch.id, building)} />
                              </PermissionGuard>
                              <PermissionGuard perm={['buildings.delete', 'property.delete']}>
                                <IconButton icon={Trash2} label="Delete building" tone="danger"
                                  onClick={() => setConfirm({ type: 'building', data: building })} />
                              </PermissionGuard>
                              <PermissionGuard perm={['floors.create', 'property.create']}>
                                <Button size="sm" icon={Plus}
                                  onClick={() => openFloor(building.id)}>Floor</Button>
                              </PermissionGuard>
                            </div>
                          </div>

                          {bFloors.length === 0 ? (
                            <p className="text-sm text-slate-500 sm:pl-11">
                              No floors yet. Add one to start creating rooms.
                            </p>
                          ) : (
                            <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-2.5 sm:pl-11">
                              {bFloors.map((fl) => (
                                <div key={fl.id} className="rounded-lg border border-line p-3.5">
                                  <div className="flex items-center justify-between gap-2 mb-1">
                                    <p className="text-sm font-medium text-slate-900">{fl.name}</p>
                                    <StatusBadge status={fl.status} dot />
                                  </div>
                                  <p className="text-xs text-slate-500 tnum">
                                    Level {fl.floor_number} · {fl.counts?.rooms || 0} rooms
                                  </p>
                                  <div className="flex gap-1.5 mt-2">
                                    <PermissionGuard perm={['floors.edit', 'property.edit']}>
                                      <IconButton icon={Pencil} label="Edit floor"
                                        onClick={() => openFloor(building.id, fl)} />
                                    </PermissionGuard>
                                    <PermissionGuard perm={['floors.delete', 'property.delete']}>
                                      <IconButton icon={Trash2} label="Delete floor" tone="danger"
                                        onClick={() => setConfirm({ type: 'floor', data: fl })} />
                                    </PermissionGuard>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}

      <Modal open={!!modal} onClose={() => setModal(null)} size="sm"
        title={modal?.mode === 'new'
          ? `Add a ${modal?.type}` : `Edit ${modal?.type === 'building' ? f.name : 'floor'}`}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>Save</Button></>}>
        {modal?.type === 'building' ? (
          <div className="space-y-4">
            <FormField label="Name" required>
              <Input value={f.name || ''} onChange={set('name')} placeholder="Block A" />
            </FormField>
            <FormField label="Code" hint="Unique within the branch. Used on bed tags.">
              <Input value={f.code || ''} onChange={set('code')} disabled={modal.mode === 'edit'}
                maxLength={20} className="uppercase" placeholder="A" />
            </FormField>
            <FormField label="Number of floors">
              <Input inputMode="numeric" className="tnum" value={f.number_of_floors ?? 1}
                onChange={set('number_of_floors')} />
            </FormField>
            <FormField label="Description">
              <Textarea rows={2} value={f.description || ''} onChange={set('description')} />
            </FormField>
            {modal.mode === 'edit' && (
              <FormField label="Status">
                <Select value={f.status || 'ACTIVE'} onChange={set('status')}>
                  {['ACTIVE', 'INACTIVE', 'UNDER_CONSTRUCTION'].map((x) => <option key={x}>{x}</option>)}
                </Select>
              </FormField>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <FormField label="Level" required hint="0 is the ground floor; negatives are basements.">
              <Input inputMode="numeric" className="tnum" value={f.floor_number ?? ''}
                onChange={set('floor_number')} disabled={modal?.mode === 'edit'} placeholder="1" />
            </FormField>
            <FormField label="Name" hint="Generated from the level if left blank.">
              <Input value={f.name || ''} onChange={set('name')} placeholder="1st Floor" />
            </FormField>
            {modal?.mode === 'edit' && (
              <FormField label="Status">
                <Select value={f.status || 'ACTIVE'} onChange={set('status')}>
                  <option>ACTIVE</option><option>INACTIVE</option>
                </Select>
              </FormField>
            )}
          </div>
        )}
      </Modal>

      <ConfirmDialog open={!!confirm} onClose={() => setConfirm(null)} tone="danger"
        title={`Delete this ${confirm?.type}?`} confirmLabel="Delete"
        message="This is refused if it still contains rooms — remove those first."
        onConfirm={remove} />
    </>
  )
}
