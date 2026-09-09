import { useState } from 'react'
import { Plus, Package, ArrowDownToLine, ArrowUpFromLine, Scale, History } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { inventoryApi } from '@/services/api/inventoryApi'
import { branchApi } from '@/services/api/branchApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard, Modal,
  FormField, Input, Select, Textarea, InlineAlert, Skeleton, ProgressBar, IconButton,
} from '@/components/ui'
import { inr, num, relative } from '@/lib/format'

const CATEGORIES = ['Housekeeping', 'Kitchen', 'Maintenance', 'Linen', 'Office', 'Other']

export default function Inventory() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [lowOnly, setLowOnly] = useState(false)
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState(null)      // 'new' | { item, mode:'adjust' }
  const [ledger, setLedger] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})

  const branches = useApi(() => branchApi.list(), [], { enabled: can('branches.view') })
  const items = useApi(
    () => inventoryApi.list({ search, category, low_only: lowOnly,
      branch_id: activeBranchId, page, page_size: 50 }),
    [search, category, lowOnly, activeBranchId, page])

  const rows = items.data?.items || []
  const pagination = items.data?.pagination
  const low = rows.filter((i) => i.is_low)
  const value = rows.reduce((a, i) => a + i.value, 0)

  const openNew = () => {
    setF({ branch_id: activeBranchId || branches.data?.items?.[0]?.id || '',
      sku: '', name: '', category: 'Housekeeping', unit: 'pcs',
      quantity: '0', minimum_stock: '0', supplier: '', purchase_price: '' })
    setModal('new')
  }
  const openAdjust = (item, txn_type) => {
    setF({ item, txn_type, quantity: '', reference: '', notes: '' })
    setModal('adjust')
  }

  const save = async () => {
    setBusy(true)
    try {
      if (modal === 'new') {
        if (!f.sku?.trim() || !f.name?.trim()) throw new Error('SKU and name are required.')
        await inventoryApi.create({
          branch_id: f.branch_id, sku: f.sku.trim(), name: f.name.trim(),
          category: f.category, unit: f.unit,
          quantity: Number(f.quantity) || 0,
          minimum_stock: Number(f.minimum_stock) || 0,
          supplier: f.supplier || null,
          purchase_price: Number(f.purchase_price) || 0 })
        success(`${f.name} added`)
      } else {
        if (!(Number(f.quantity) > 0)) throw new Error('Enter a quantity.')
        const updated = await inventoryApi.adjust(f.item.id, {
          txn_type: f.txn_type, quantity: Number(f.quantity),
          reference: f.reference || null, notes: f.notes || null })
        success(`${updated.name}: now ${updated.quantity} ${updated.unit}`)
      }
      setModal(null)
      items.reload()
    } catch (err) { error('That did not work', err.message) }
    finally { setBusy(false) }
  }

  const openLedger = async (item) => {
    try { setLedger({ item, rows: await inventoryApi.transactions(item.id) }) }
    catch (err) { error('Could not load the ledger', err.message) }
  }

  const columns = [
    { key: 'name', header: 'Item',
      render: (i) => <div><p className="font-medium text-slate-900">{i.name}</p>
        <p className="text-xs text-slate-500 font-mono">{i.sku}</p></div> },
    { key: 'category', header: 'Category',
      render: (i) => <StatusBadge status={i.category} tone="slate" /> },
    { key: 'quantity', header: 'In stock', align: 'right',
      render: (i) => (
        <div className="min-w-[96px]">
          <p className={`tnum text-sm ${i.is_low ? 'text-rose-600 font-medium' : 'text-slate-800'}`}>
            {i.quantity} {i.unit}
          </p>
          <ProgressBar value={Math.min(i.quantity, i.minimum_stock * 2 || i.quantity || 1)}
            max={i.minimum_stock * 2 || i.quantity || 1} className="mt-1"
            tone={i.is_low ? 'rose' : 'brand'} />
        </div>
      ) },
    { key: 'minimum_stock', header: 'Minimum', align: 'right',
      render: (i) => <span className="tnum text-slate-600">{i.minimum_stock}</span> },
    { key: 'value', header: 'Value', align: 'right', hideBelow: 'xl',
      render: (i) => <span className="tnum text-slate-700">{inr(i.value)}</span> },
    { key: 'actions', header: '', sortable: false, align: 'right',
      render: (i) => (
        <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          <PermissionGuard perm={['inventory.adjust', 'inventory.manage']}>
            <IconButton icon={ArrowDownToLine} label="Stock in"
              onClick={() => openAdjust(i, 'STOCK_IN')} />
            <IconButton icon={ArrowUpFromLine} label="Stock out"
              onClick={() => openAdjust(i, 'STOCK_OUT')} />
            <IconButton icon={Scale} label="Stock take"
              onClick={() => openAdjust(i, 'ADJUSTMENT')} />
          </PermissionGuard>
          <IconButton icon={History} label="Ledger" onClick={() => openLedger(i)} />
        </div>
      ) },
  ]

  return (
    <>
      <PageHeader title="Inventory" subtitle="Consumables and supplies, with a full stock ledger."
        actions={<PermissionGuard perm={['inventory.create', 'inventory.manage']}>
          <Button variant="primary" icon={Plus} onClick={openNew}>Add item</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Items tracked" value={num(pagination?.total ?? rows.length)}
          icon={Package} tone="brand" />
        <StatCard label="Below minimum" value={num(low.length)}
          tone={low.length ? 'rose' : 'emerald'} />
        <StatCard label="Stock value" value={inr(value)} tone="violet" />
        <StatCard label="Categories"
          value={num(new Set(rows.map((i) => i.category)).size)} tone="slate" />
      </div>

      {low.length > 0 && (
        <InlineAlert tone="warn" className="mb-4"
          title={`${low.length} item${low.length === 1 ? '' : 's'} at or below minimum`}>
          {low.slice(0, 4).map((i) => `${i.name} (${i.quantity} ${i.unit})`).join(', ')}
          {low.length > 4 ? ` and ${low.length - 4} more.` : '.'}
        </InlineAlert>
      )}

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={(v) => { setSearch(v); setPage(1) }}
            searchPlaceholder="Search item or SKU…"
            filters={[
              { key: 'category', label: 'Category', value: category,
                onChange: (v) => { setCategory(v); setPage(1) }, options: CATEGORIES },
              { key: 'low', label: 'Stock', value: lowOnly ? 'low' : 'all',
                onChange: (v) => { setLowOnly(v === 'low'); setPage(1) },
                options: [{ value: 'low', label: 'Below minimum' }] },
            ]} />
        </div>

        {items.error ? (
          <InlineAlert tone="error" className="m-4">{items.error.message}</InlineAlert>
        ) : items.loading && !items.data ? (
          <div className="p-4 space-y-2">{[0, 1, 2].map((i) =>
            <Skeleton key={i} className="h-14" />)}</div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={50}
            mobileCard={(i) => (
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900 truncate">{i.name}</p>
                  <p className="text-xs text-slate-500">{i.category} · {i.sku}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className={`text-sm tnum ${i.is_low ? 'text-rose-600' : 'text-slate-900'}`}>
                    {i.quantity} {i.unit}</p>
                  {i.is_low && <StatusBadge status="Low" tone="rose" />}
                </div>
              </div>
            )}
            empty={<EmptyState icon={Package} title="Nothing tracked yet"
              message="Add the consumables you buy regularly." />} />
        )}
      </Card>

      <Modal open={!!modal} onClose={() => setModal(null)} size="sm"
        title={modal === 'new' ? 'Add an item'
          : f.txn_type === 'STOCK_IN' ? `Stock in — ${f.item?.name}`
            : f.txn_type === 'STOCK_OUT' ? `Stock out — ${f.item?.name}`
              : `Stock take — ${f.item?.name}`}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>Save</Button></>}>
        {modal === 'new' ? (
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
            <div className="grid grid-cols-2 gap-3">
              <FormField label="SKU" required>
                <Input value={f.sku} className="uppercase"
                  onChange={(e) => setF({ ...f, sku: e.target.value })} />
              </FormField>
              <FormField label="Category">
                <Select value={f.category}
                  onChange={(e) => setF({ ...f, category: e.target.value })}>
                  {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                </Select>
              </FormField>
            </div>
            <FormField label="Name" required>
              <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
            </FormField>
            <div className="grid grid-cols-3 gap-3">
              <FormField label="Unit">
                <Input value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} />
              </FormField>
              <FormField label="Opening qty">
                <Input inputMode="numeric" className="tnum" value={f.quantity}
                  onChange={(e) => setF({ ...f, quantity: e.target.value })} />
              </FormField>
              <FormField label="Minimum">
                <Input inputMode="numeric" className="tnum" value={f.minimum_stock}
                  onChange={(e) => setF({ ...f, minimum_stock: e.target.value })} />
              </FormField>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <FormField label="Supplier">
                <Input value={f.supplier} onChange={(e) => setF({ ...f, supplier: e.target.value })} />
              </FormField>
              <FormField label="Unit price">
                <Input inputMode="numeric" className="tnum" value={f.purchase_price}
                  onChange={(e) => setF({ ...f, purchase_price: e.target.value })} />
              </FormField>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-lg bg-slate-50 border border-line p-3.5">
              <p className="text-sm text-slate-700">
                Currently <span className="tnum font-medium text-slate-900">
                  {f.item?.quantity} {f.item?.unit}</span> in stock.
              </p>
            </div>
            <FormField label={f.txn_type === 'ADJUSTMENT' ? 'Counted quantity' : 'Quantity'}
              required
              hint={f.txn_type === 'ADJUSTMENT'
                ? 'The number actually on the shelf — this sets the level rather than adding to it.'
                : undefined}>
              <Input inputMode="numeric" className="tnum" value={f.quantity}
                onChange={(e) => setF({ ...f, quantity: e.target.value })} />
            </FormField>
            <FormField label="Reference" hint="Bill number, or who took it.">
              <Input value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} />
            </FormField>
            <FormField label="Notes">
              <Textarea rows={2} value={f.notes}
                onChange={(e) => setF({ ...f, notes: e.target.value })} />
            </FormField>
            {f.txn_type === 'STOCK_OUT' && (
              <InlineAlert tone="info">
                Stock cannot go below zero — the server refuses the movement rather
                than letting the count drift.
              </InlineAlert>
            )}
          </div>
        )}
      </Modal>

      <Modal open={!!ledger} onClose={() => setLedger(null)} size="md"
        title={`Stock ledger — ${ledger?.item?.name}`}
        subtitle="Every movement, newest first"
        footer={<Button variant="primary" onClick={() => setLedger(null)}>Close</Button>}>
        {ledger && (ledger.rows.length === 0 ? (
          <EmptyState compact title="No movements yet" />
        ) : (
          <div className="divide-y divide-line max-h-96 overflow-y-auto">
            {ledger.rows.map((t) => (
              <div key={t.id} className="py-2.5 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-slate-800">
                    {t.txn_type.replace('_', ' ')}
                    {t.reference ? ` · ${t.reference}` : ''}
                  </p>
                  <p className="text-2xs text-slate-500">
                    {t.notes || relative(t.created_at)}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className={`text-sm tnum font-medium ${
                    t.quantity_delta >= 0 ? 'text-emerald-700' : 'text-rose-600'}`}>
                    {t.quantity_delta >= 0 ? '+' : ''}{t.quantity_delta}
                  </p>
                  <p className="text-2xs text-slate-500 tnum">→ {t.balance_after}</p>
                </div>
              </div>
            ))}
          </div>
        ))}
      </Modal>
    </>
  )
}
