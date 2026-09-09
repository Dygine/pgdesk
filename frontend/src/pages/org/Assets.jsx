import { useState } from 'react'
import { Plus, Boxes, Pencil } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { assetApi } from '@/services/api/assetApi'
import { branchApi } from '@/services/api/branchApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard, Modal,
  FormField, Input, Select, Textarea, InlineAlert, Skeleton, IconButton,
} from '@/components/ui'
import { inr, num, dateFmt } from '@/lib/format'

const CATEGORIES = ['Appliance', 'Furniture', 'Electrical', 'Security', 'Network',
  'Housekeeping', 'Safety', 'Other']
const STATUSES = ['ACTIVE', 'MAINTENANCE', 'DAMAGED', 'LOST', 'DISPOSED']
const TONE = { ACTIVE: 'emerald', MAINTENANCE: 'amber', DAMAGED: 'rose',
  LOST: 'rose', DISPOSED: 'slate' }

export default function Assets() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [status, setStatus] = useState('all')
  const [modal, setModal] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})

  const branches = useApi(() => branchApi.list(), [], { enabled: can('branches.view') })
  const assets = useApi(
    () => assetApi.list({ search, category, status, branch_id: activeBranchId, page_size: 100 }),
    [search, category, status, activeBranchId])

  const rows = assets.data?.items || []
  const value = rows.reduce((a, x) => a + Number(x.purchase_price || 0), 0)
  const needsAttention = rows.filter((a) => ['MAINTENANCE', 'DAMAGED', 'LOST'].includes(a.status))

  const openNew = () => {
    setF({ branch_id: activeBranchId || branches.data?.items?.[0]?.id || '',
      name: '', category: 'Appliance', purchase_price: '', purchase_date: '',
      warranty_until: '', location: '', status: 'ACTIVE', notes: '' })
    setModal('new')
  }
  const openEdit = (a) => { setF({ ...a }); setModal(a) }

  const save = async () => {
    if (!f.name?.trim()) return error('Give the asset a name.')
    setBusy(true)
    try {
      if (modal === 'new') {
        await assetApi.create({
          branch_id: f.branch_id, name: f.name.trim(), category: f.category,
          purchase_price: Number(f.purchase_price) || 0,
          purchase_date: f.purchase_date || null,
          warranty_until: f.warranty_until || null,
          location: f.location || null, status: f.status, notes: f.notes || null })
        success(`${f.name} added`)
      } else {
        await assetApi.update(modal.id, {
          name: f.name.trim(), category: f.category,
          purchase_price: Number(f.purchase_price) || 0,
          purchase_date: f.purchase_date || null,
          warranty_until: f.warranty_until || null,
          location: f.location || null, status: f.status, notes: f.notes || null })
        success('Asset updated')
      }
      setModal(null)
      assets.reload()
    } catch (err) { error('That did not work', err.message) }
    finally { setBusy(false) }
  }

  const columns = [
    { key: 'name', header: 'Asset',
      render: (a) => <div><p className="font-medium text-slate-900">{a.name}</p>
        <p className="text-xs text-slate-500 font-mono">{a.asset_code}</p></div> },
    { key: 'category', header: 'Category',
      render: (a) => <StatusBadge status={a.category} tone="slate" /> },
    { key: 'location', header: 'Where', sortable: false,
      render: (a) => <span className="text-sm text-slate-600">{a.location || '—'}</span> },
    { key: 'purchase_date', header: 'Bought',
      render: (a) => <span className="text-sm tnum text-slate-600">
        {a.purchase_date ? dateFmt(a.purchase_date) : '—'}</span> },
    { key: 'purchase_price', header: 'Cost', align: 'right',
      render: (a) => <span className="tnum text-slate-800">{inr(a.purchase_price)}</span> },
    { key: 'status', header: 'Status',
      render: (a) => <StatusBadge status={a.status} tone={TONE[a.status]} dot /> },
    { key: 'actions', header: '', sortable: false, align: 'right',
      render: (a) => (
        <PermissionGuard perm="assets.manage">
          <div onClick={(e) => e.stopPropagation()}>
            <IconButton icon={Pencil} label="Edit asset" onClick={() => openEdit(a)} />
          </div>
        </PermissionGuard>
      ) },
  ]

  return (
    <>
      <PageHeader title="Assets" subtitle="Equipment and furniture, and what condition it is in."
        actions={<PermissionGuard perm={['assets.create', 'assets.manage']}>
          <Button variant="primary" icon={Plus} onClick={openNew}>Add asset</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Assets" value={num(rows.length)} icon={Boxes} tone="brand" />
        <StatCard label="In service"
          value={num(rows.filter((a) => a.status === 'ACTIVE').length)} tone="emerald" />
        <StatCard label="Needs attention" value={num(needsAttention.length)}
          tone={needsAttention.length ? 'amber' : 'slate'} />
        <StatCard label="Purchase value" value={inr(value)} tone="violet" />
      </div>

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={setSearch}
            searchPlaceholder="Search asset or code…"
            filters={[
              { key: 'category', label: 'Category', value: category,
                onChange: setCategory, options: CATEGORIES },
              { key: 'status', label: 'Status', value: status,
                onChange: setStatus, options: STATUSES },
            ]} />
        </div>

        {assets.error ? (
          <InlineAlert tone="error" className="m-4">{assets.error.message}</InlineAlert>
        ) : assets.loading && !assets.data ? (
          <div className="p-4 space-y-2">{[0, 1, 2].map((i) =>
            <Skeleton key={i} className="h-14" />)}</div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={50}
            mobileCard={(a) => (
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900 truncate">{a.name}</p>
                  <p className="text-xs text-slate-500">{a.category} · {a.location || '—'}</p>
                </div>
                <StatusBadge status={a.status} tone={TONE[a.status]} />
              </div>
            )}
            empty={<EmptyState icon={Boxes} title="No assets recorded"
              message="Track the equipment you own so repairs and warranties are visible." />} />
        )}
      </Card>

      <Modal open={!!modal} onClose={() => setModal(null)} size="sm"
        title={modal === 'new' ? 'Add an asset' : `Edit ${f.name}`}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>Save</Button></>}>
        <div className="space-y-4">
          {modal === 'new' && (
            <FormField label="Branch" required>
              <Select value={f.branch_id || ''}
                onChange={(e) => setF({ ...f, branch_id: e.target.value })}>
                <option value="">Choose…</option>
                {(branches.data?.items || []).map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </Select>
            </FormField>
          )}
          <FormField label="Name" required>
            <Input value={f.name || ''} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Category">
              <Select value={f.category || 'Appliance'}
                onChange={(e) => setF({ ...f, category: e.target.value })}>
                {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
              </Select>
            </FormField>
            <FormField label="Status">
              <Select value={f.status || 'ACTIVE'}
                onChange={(e) => setF({ ...f, status: e.target.value })}>
                {STATUSES.map((s) => <option key={s}>{s}</option>)}
              </Select>
            </FormField>
            <FormField label="Purchase price">
              <Input inputMode="numeric" className="tnum" value={f.purchase_price ?? ''}
                onChange={(e) => setF({ ...f, purchase_price: e.target.value })} />
            </FormField>
            <FormField label="Purchased on">
              <Input type="date" value={f.purchase_date || ''}
                onChange={(e) => setF({ ...f, purchase_date: e.target.value })} />
            </FormField>
            <FormField label="Warranty until">
              <Input type="date" value={f.warranty_until || ''}
                onChange={(e) => setF({ ...f, warranty_until: e.target.value })} />
            </FormField>
            <FormField label="Location">
              <Input value={f.location || ''}
                onChange={(e) => setF({ ...f, location: e.target.value })} />
            </FormField>
          </div>
          <FormField label="Notes">
            <Textarea rows={2} value={f.notes || ''}
              onChange={(e) => setF({ ...f, notes: e.target.value })} />
          </FormField>
        </div>
      </Modal>
    </>
  )
}
