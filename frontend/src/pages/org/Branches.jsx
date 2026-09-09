import { useState } from 'react'
import { Plus, Building2, Pencil, Power } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { branchApi } from '@/services/api/branchApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, StatCard, StatusBadge, EmptyState, FilterBar, Modal, FormField,
  Input, Select, InlineAlert, ProgressBar, Skeleton, ConfirmDialog,
} from '@/components/ui'
import { num } from '@/lib/format'

const BLANK = { name: '', code: '', address: '', city: 'Bengaluru', state: 'Karnataka',
  pincode: '', contact_number: '' }

export default function Branches() {
  const { can } = useAuth()
  const { success, error } = useToast()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [modal, setModal] = useState(null)      // 'new' | branch object
  const [f, setF] = useState(BLANK)
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null)

  const branches = useApi(() => branchApi.list({ search, status }), [search, status])
  const plan = useApi(() => subscriptionApi.mine(), [], { enabled: can('dashboard.view') })

  const rows = branches.data?.items || []
  const limit = plan.data?.limits?.branches
  const used = plan.data?.usage?.branches ?? rows.length
  const atLimit = limit != null && used >= limit

  const set = (k) => (e) => {
    setF((x) => ({ ...x, [k]: e.target.value }))
    setErrs((x) => ({ ...x, [k]: undefined }))
  }

  const openNew = () => { setF(BLANK); setErrs({}); setModal('new') }
  const openEdit = (b) => { setF({ ...BLANK, ...b }); setErrs({}); setModal(b) }

  const save = async () => {
    const e = {}
    if (f.name.trim().length < 2) e.name = 'Give the branch a name.'
    if (modal === 'new' && !f.code.trim()) e.code = 'A short code is required.'
    setErrs(e)
    if (Object.keys(e).length) return

    setBusy(true)
    try {
      if (modal === 'new') {
        await branchApi.create({ ...f, code: f.code.trim().toUpperCase() })
        success(`${f.name} created`)
      } else {
        await branchApi.update(modal.id, f)
        success(`${f.name} updated`)
      }
      setModal(null)
      branches.reload()
      plan.reload()
    } catch (err) {
      error(modal === 'new' ? 'Could not create the branch' : 'Could not save', err.message)
    } finally { setBusy(false) }
  }

  const deactivate = async () => {
    try {
      await branchApi.deactivate(confirm.id)
      success(`${confirm.name} deactivated`)
      branches.reload()
    } catch (err) {
      error('Could not deactivate', err.message)
    } finally { setConfirm(null) }
  }

  const totals = rows.reduce((a, b) => ({
    rooms: a.rooms + (b.counts?.rooms || 0),
    beds: a.beds + (b.counts?.beds || 0),
    occupied: a.occupied + (b.counts?.occupied || 0),
  }), { rooms: 0, beds: 0, occupied: 0 })

  return (
    <>
      <PageHeader title="Branches"
        subtitle="Each physical location you operate. Everything else hangs off a branch."
        actions={<PermissionGuard perm="branches.create">
          <Button variant="primary" icon={Plus} onClick={openNew} disabled={atLimit}>Add branch</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Branches" value={`${used}${limit ? ` / ${limit}` : ''}`}
          icon={Building2} tone={atLimit ? 'rose' : 'brand'}
          footer={limit ? <ProgressBar value={used} max={limit}
            tone={atLimit ? 'rose' : 'brand'} /> : undefined} />
        <StatCard label="Rooms" value={num(totals.rooms)} tone="violet" />
        <StatCard label="Beds" value={num(totals.beds)} tone="blue" />
        <StatCard label="Occupied" value={num(totals.occupied)} tone="emerald"
          sub={totals.beds ? `${Math.round(totals.occupied / totals.beds * 100)}% of beds` : undefined} />
      </div>

      {atLimit && (
        <InlineAlert tone="warn" className="mb-4" title="Branch limit reached">
          Your plan allows {limit} branches and all {used} are in use. The server refuses
          another regardless of what the UI shows — ask the platform administrator to upgrade.
        </InlineAlert>
      )}

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={setSearch}
            searchPlaceholder="Search name, code or city…"
            filters={[{ key: 'status', label: 'Status', value: status, onChange: setStatus,
              options: ['ACTIVE', 'INACTIVE'] }]} />
        </div>

        {branches.error ? (
          <InlineAlert tone="error" className="m-4">{branches.error.message}</InlineAlert>
        ) : branches.loading && !branches.data ? (
          <div className="p-4 grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-40" />)}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState icon={Building2} title="No branches yet"
            message="Add your first branch, then buildings, floors, rooms and beds underneath it."
            action={<PermissionGuard perm="branches.create">
              <Button variant="primary" icon={Plus} onClick={openNew}>Add branch</Button>
            </PermissionGuard>} />
        ) : (
          <div className="p-4 grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {rows.map((b) => {
              const beds = b.counts?.beds || 0
              const occ = b.counts?.occupied || 0
              return (
                <div key={b.id} className="rounded-lg border border-line p-4">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-slate-900 truncate">{b.name}</p>
                      <p className="text-xs text-slate-500">{b.code} · {b.city || '—'}</p>
                    </div>
                    <StatusBadge status={b.status} dot />
                  </div>

                  <div className="grid grid-cols-4 gap-2 text-center py-3 border-y border-line">
                    {[['Buildings', b.counts?.buildings], ['Floors', b.counts?.floors],
                      ['Rooms', b.counts?.rooms], ['Beds', beds]].map(([k, v]) => (
                      <div key={k}>
                        <p className="text-sm font-semibold text-slate-900 tnum">{v ?? 0}</p>
                        <p className="text-2xs text-slate-500">{k}</p>
                      </div>
                    ))}
                  </div>

                  <div className="mt-3">
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-slate-500">Occupancy</span>
                      <span className="tnum text-slate-900">
                        {occ}/{beds} {beds ? `(${Math.round(occ / beds * 100)}%)` : ''}
                      </span>
                    </div>
                    <ProgressBar value={occ} max={beds || 1} />
                  </div>

                  <div className="mt-3 flex gap-2">
                    <PermissionGuard perm="branches.edit">
                      <Button size="sm" icon={Pencil} className="flex-1"
                        onClick={() => openEdit(b)}>Edit</Button>
                    </PermissionGuard>
                    {b.status === 'ACTIVE' && (
                      <PermissionGuard perm="branches.delete">
                        <Button size="sm" icon={Power} onClick={() => setConfirm(b)}>Deactivate</Button>
                      </PermissionGuard>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Card>

      <Modal open={!!modal} onClose={() => setModal(null)} size="md"
        title={modal === 'new' ? 'Add a branch' : `Edit ${f.name}`}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>
            {modal === 'new' ? 'Create branch' : 'Save changes'}</Button></>}>
        <div className="grid sm:grid-cols-2 gap-4">
          <FormField label="Branch name" required error={errs.name} className="sm:col-span-2">
            <Input value={f.name} onChange={set('name')} error={errs.name} placeholder="Koramangala" />
          </FormField>
          <FormField label="Short code" required error={errs.code}
            hint="Unique within your PG. Used on bed tags.">
            <Input value={f.code} onChange={set('code')} error={errs.code}
              disabled={modal !== 'new'} maxLength={10} className="uppercase" placeholder="KOR" />
          </FormField>
          <FormField label="Contact number">
            <Input value={f.contact_number} onChange={set('contact_number')} />
          </FormField>
          <FormField label="Address" className="sm:col-span-2">
            <Input value={f.address} onChange={set('address')} />
          </FormField>
          <FormField label="City"><Input value={f.city} onChange={set('city')} /></FormField>
          <FormField label="State"><Input value={f.state} onChange={set('state')} /></FormField>
          <FormField label="Pincode"><Input value={f.pincode} onChange={set('pincode')} /></FormField>
          {modal !== 'new' && (
            <FormField label="Status">
              <Select value={f.status || 'ACTIVE'} onChange={set('status')}>
                <option value="ACTIVE">ACTIVE</option><option value="INACTIVE">INACTIVE</option>
              </Select>
            </FormField>
          )}
        </div>
      </Modal>

      <ConfirmDialog open={!!confirm} onClose={() => setConfirm(null)}
        title={`Deactivate ${confirm?.name}?`} tone="danger" confirmLabel="Deactivate"
        message="The branch stops appearing in day-to-day screens but nothing is deleted. Occupied beds must be checked out first."
        onConfirm={deactivate} />
    </>
  )
}
