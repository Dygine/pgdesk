import { useState } from 'react'
import { Plus, Receipt, Wand2, Ban, IndianRupee } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { invoiceApi } from '@/services/api/invoiceApi'
import { rentApi } from '@/services/api/rentApi'
import { residentApi } from '@/services/api/residentApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard, Modal,
  FormField, Input, Select, Textarea, InlineAlert, Skeleton, ConfirmDialog, IconButton,
} from '@/components/ui'
import { inr, num, dateFmt, today } from '@/lib/format'

const STATUSES = ['PENDING', 'PARTIAL', 'PAID', 'OVERDUE', 'CANCELLED']
const KINDS = ['RENT', 'FOOD', 'LAUNDRY', 'ELECTRICITY', 'MAINTENANCE', 'DEPOSIT',
  'LATE_FEE', 'DISCOUNT', 'OTHER']

export default function Invoices() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState(null)
  const [cancelling, setCancelling] = useState(null)
  const [busy, setBusy] = useState(false)
  const [genOpen, setGenOpen] = useState(false)
  const [f, setF] = useState({ resident_id: '', due_date: '', notes: '', items: [] })

  const summary = useApi(() => rentApi.summary({ branch_id: activeBranchId }),
    [activeBranchId], { enabled: can('rent.view') || can('invoices.view') })
  const residents = useApi(
    () => residentApi.list({ status: 'live', branch_id: activeBranchId, page_size: 200 }),
    [activeBranchId], { enabled: can('customers.view') })
  const invoices = useApi(
    () => invoiceApi.list({ search, status, branch_id: activeBranchId, page, page_size: 25 }),
    [search, status, activeBranchId, page])

  const rows = invoices.data?.items || []
  const pagination = invoices.data?.pagination
  const s = summary.data

  const openNew = () => {
    setF({ resident_id: '', due_date: '', notes: '',
      items: [{ kind: 'RENT', description: '', quantity: 1, unit_price: '' }] })
    setOpen(true)
  }
  const setItem = (i, k, v) => setF((x) => ({
    ...x, items: x.items.map((it, j) => (j === i ? { ...it, [k]: v } : it)) }))
  const addLine = () => setF((x) => ({
    ...x, items: [...x.items, { kind: 'OTHER', description: '', quantity: 1, unit_price: '' }] }))
  const dropLine = (i) => setF((x) => ({
    ...x, items: x.items.filter((_, j) => j !== i) }))

  const total = f.items.reduce(
    (a, it) => a + (Number(it.quantity) || 0) * (Number(it.unit_price) || 0), 0)

  const save = async () => {
    if (!f.resident_id) return error('Choose a resident.')
    const items = f.items.filter((it) => it.description.trim() && Number(it.unit_price) > 0)
    if (!items.length) return error('Add at least one line with a description and an amount.')
    setBusy(true)
    try {
      const created = await invoiceApi.create({
        resident_id: f.resident_id,
        due_date: f.due_date || null, notes: f.notes || null,
        items: items.map((it) => ({
          kind: it.kind, description: it.description.trim(),
          quantity: Number(it.quantity) || 1, unit_price: Number(it.unit_price) })),
      })
      success(`Invoice ${created.invoice_number} raised`)
      setOpen(false)
      invoices.reload(); summary.reload()
    } catch (err) { error('Could not raise the invoice', err.message) }
    finally { setBusy(false) }
  }

  const generate = async () => {
    setBusy(true)
    try {
      const r = await rentApi.generate({ branch_id: activeBranchId })
      success(`${r.created} invoice${r.created === 1 ? '' : 's'} created`,
        r.skipped ? `${r.skipped} already existed for this month.` : undefined)
      setGenOpen(false)
      invoices.reload(); summary.reload()
    } catch (err) { error('Rent run failed', err.message) }
    finally { setBusy(false) }
  }

  const cancel = async () => {
    try {
      await invoiceApi.cancel(cancelling.id, 'Cancelled from the invoices screen')
      success('Invoice cancelled')
      invoices.reload(); summary.reload()
    } catch (err) { error('Could not cancel', err.message) }
    finally { setCancelling(null) }
  }

  const columns = [
    { key: 'invoice_number', header: 'Invoice',
      render: (i) => <div><p className="font-medium text-slate-900">{i.invoice_number}</p>
        <p className="text-xs text-slate-500 truncate">{i.resident}</p></div> },
    { key: 'invoice_date', header: 'Raised',
      render: (i) => <span className="text-sm tnum text-slate-600">{dateFmt(i.invoice_date)}</span> },
    { key: 'due_date', header: 'Due',
      render: (i) => <span className={`text-sm tnum ${
        i.days_overdue > 0 ? 'text-rose-600' : 'text-slate-600'}`}>
        {dateFmt(i.due_date)}{i.days_overdue > 0 ? ` · ${i.days_overdue}d` : ''}</span> },
    { key: 'total', header: 'Total', align: 'right',
      render: (i) => <span className="tnum text-slate-700">{inr(i.total)}</span> },
    { key: 'balance', header: 'Balance', align: 'right',
      render: (i) => <span className={`tnum font-medium ${
        Number(i.balance) > 0 ? 'text-slate-900' : 'text-emerald-700'}`}>{inr(i.balance)}</span> },
    { key: 'status', header: 'Status', render: (i) => <StatusBadge status={i.status} dot /> },
    { key: 'actions', header: '', sortable: false, align: 'right',
      render: (i) => (
        <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          {i.status !== 'CANCELLED' && i.status !== 'PAID' && (
            <PermissionGuard perm={['invoices.cancel', 'invoices.delete']}>
              <IconButton icon={Ban} label="Cancel invoice" tone="danger"
                onClick={() => setCancelling(i)} />
            </PermissionGuard>
          )}
        </div>
      ) },
  ]

  return (
    <>
      <PageHeader title="Invoices" subtitle="What has been billed, and what is still owed."
        actions={<>
          <PermissionGuard perm={['rent.generate', 'invoices.create']}>
            <Button icon={Wand2} onClick={() => setGenOpen(true)}>Generate rent</Button>
          </PermissionGuard>
          <PermissionGuard perm="invoices.create">
            <Button variant="primary" icon={Plus} onClick={openNew}>New invoice</Button>
          </PermissionGuard>
        </>} />

      {s && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
          <StatCard label="Billed this month" value={inr(s.expected)} icon={Receipt} tone="brand" />
          <StatCard label="Collected" value={inr(s.collected)} icon={IndianRupee} tone="emerald"
            sub={`${s.collection_rate}% of billed`} />
          <StatCard label="Outstanding" value={inr(s.outstanding)} tone="amber" />
          <StatCard label="Overdue" value={inr(s.overdue)}
            tone={s.overdue > 0 ? 'rose' : 'slate'} />
        </div>
      )}

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={(v) => { setSearch(v); setPage(1) }}
            searchPlaceholder="Search invoice number or resident…"
            filters={[{ key: 'status', label: 'Status', value: status,
              onChange: (v) => { setStatus(v); setPage(1) }, options: STATUSES }]} />
        </div>

        {invoices.error ? (
          <InlineAlert tone="error" className="m-4">{invoices.error.message}</InlineAlert>
        ) : invoices.loading && !invoices.data ? (
          <div className="p-4 space-y-2">{[0, 1, 2, 3].map((i) =>
            <Skeleton key={i} className="h-14" />)}</div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={25}
            onRowClick={async (i) => {
              try { setDetail(await invoiceApi.get(i.id)) }
              catch (err) { error('Could not open the invoice', err.message) }
            }}
            mobileCard={(i) => (
              <div className="space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900">{i.invoice_number}</p>
                    <p className="text-xs text-slate-500 truncate">{i.resident}</p>
                  </div>
                  <StatusBadge status={i.status} />
                </div>
                <div className="flex justify-between text-xs tnum">
                  <span className="text-slate-500">Due {dateFmt(i.due_date)}</span>
                  <span className="font-medium text-slate-900">{inr(i.balance)} due</span>
                </div>
              </div>
            )}
            empty={<EmptyState icon={Receipt} title="No invoices match"
              message="Generate this month's rent, or raise one by hand." />} />
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between">
            <p className="text-xs text-slate-500 tnum">
              Page {pagination.page} of {pagination.total_pages} · {pagination.total} invoices
            </p>
            <div className="flex gap-2">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" disabled={page >= pagination.total_pages}
                onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      {/* ------------------------------------------------------- new invoice */}
      <Modal open={open} onClose={() => setOpen(false)} size="lg" title="Raise an invoice"
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>
            Raise invoice · {inr(total)}</Button></>}>
        <div className="space-y-5">
          <div className="grid sm:grid-cols-2 gap-4">
            <FormField label="Resident" required>
              <Select value={f.resident_id}
                onChange={(e) => setF({ ...f, resident_id: e.target.value })}>
                <option value="">Choose…</option>
                {(residents.data?.items || []).map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.full_name}{r.placement?.room ? ` — room ${r.placement.room}` : ''}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField label="Due date" hint="Seven days from today if left blank.">
              <Input type="date" value={f.due_date}
                onChange={(e) => setF({ ...f, due_date: e.target.value })} />
            </FormField>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2 pb-2 border-b border-line">
              <p className="text-[13px] font-semibold text-slate-800">Lines</p>
              <Button size="sm" icon={Plus} onClick={addLine}>Add line</Button>
            </div>
            <div className="space-y-2">
              {f.items.map((it, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-end">
                  <div className="col-span-12 sm:col-span-3">
                    <Select value={it.kind} onChange={(e) => setItem(i, 'kind', e.target.value)}>
                      {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                    </Select>
                  </div>
                  <div className="col-span-7 sm:col-span-5">
                    <Input value={it.description} placeholder="Description"
                      onChange={(e) => setItem(i, 'description', e.target.value)} />
                  </div>
                  <div className="col-span-2">
                    <Input inputMode="numeric" className="tnum" value={it.quantity}
                      onChange={(e) => setItem(i, 'quantity', e.target.value)} />
                  </div>
                  <div className="col-span-2 sm:col-span-2 flex gap-1">
                    <Input inputMode="numeric" className="tnum" value={it.unit_price}
                      placeholder="0" onChange={(e) => setItem(i, 'unit_price', e.target.value)} />
                    {f.items.length > 1 && (
                      <IconButton icon={Ban} label="Remove line" tone="danger"
                        onClick={() => dropLine(i)} />
                    )}
                  </div>
                </div>
              ))}
            </div>
            <p className="text-right text-sm font-semibold text-slate-900 tnum mt-3">
              Total {inr(total)}
            </p>
          </div>

          <FormField label="Notes">
            <Textarea rows={2} value={f.notes}
              onChange={(e) => setF({ ...f, notes: e.target.value })} />
          </FormField>
        </div>
      </Modal>

      {/* ---------------------------------------------------------- detail */}
      <Modal open={!!detail} onClose={() => setDetail(null)} size="md"
        title={detail?.invoice_number} subtitle={detail?.resident}
        footer={<Button variant="primary" onClick={() => setDetail(null)}>Close</Button>}>
        {detail && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-sm">
              {[['Raised', dateFmt(detail.invoice_date)], ['Due', dateFmt(detail.due_date)],
                ['Total', inr(detail.total)], ['Paid', inr(detail.paid_amount)],
                ['Balance', inr(detail.balance)], ['Status', detail.status]].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-2">
                  <span className="text-slate-500">{k}</span>
                  <span className="tnum text-slate-900">{v}</span>
                </div>
              ))}
            </div>
            <div>
              <p className="text-xs font-medium text-slate-700 mb-1.5">Lines</p>
              <div className="divide-y divide-line rounded-lg border border-line">
                {detail.items.map((it) => (
                  <div key={it.id} className="px-3 py-2 flex justify-between gap-3">
                    <span className="text-sm text-slate-700 truncate">{it.description}</span>
                    <span className="text-sm tnum text-slate-900 shrink-0">{inr(it.amount)}</span>
                  </div>
                ))}
              </div>
            </div>
            {detail.payments.length > 0 && (
              <div>
                <p className="text-xs font-medium text-slate-700 mb-1.5">Payments</p>
                <div className="divide-y divide-line rounded-lg border border-line">
                  {detail.payments.map((p) => (
                    <div key={p.id} className="px-3 py-2 flex items-center justify-between gap-3">
                      <span className="text-sm text-slate-700">
                        {p.payment_number} · {p.method}</span>
                      <span className="flex items-center gap-2 shrink-0">
                        <span className="text-sm tnum text-slate-900">{inr(p.amount)}</span>
                        <StatusBadge status={p.status} />
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>

      <ConfirmDialog open={genOpen} onClose={() => setGenOpen(false)} loading={busy}
        title="Generate this month's rent?" confirmLabel="Generate"
        message="One invoice per active resident with a rent amount. Running it twice adds nothing the second time."
        onConfirm={generate} />

      <ConfirmDialog open={!!cancelling} onClose={() => setCancelling(null)} tone="danger"
        title={`Cancel ${cancelling?.invoice_number}?`} confirmLabel="Cancel invoice"
        message="Refused if verified payments exist against it — refund those first."
        onConfirm={cancel} />
    </>
  )
}
