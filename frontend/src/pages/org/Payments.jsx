import { useState } from 'react'
import { Plus, IndianRupee, ShieldCheck, ShieldX, Undo2 } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { paymentApi } from '@/services/api/paymentApi'
import { invoiceApi } from '@/services/api/invoiceApi'
import { rentApi } from '@/services/api/rentApi'
import { residentApi } from '@/services/api/residentApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard, Modal,
  FormField, Input, Select, Textarea, Checkbox, InlineAlert, Skeleton, IconButton,
} from '@/components/ui'
import { inr, num, dateFmt, today } from '@/lib/format'

const METHODS = ['CASH', 'UPI', 'BANK_TRANSFER', 'CARD', 'ONLINE', 'CHEQUE', 'OTHER']
const STATUSES = ['PENDING', 'VERIFIED', 'REJECTED', 'REFUNDED']

export default function Payments() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [method, setMethod] = useState('all')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})

  const summary = useApi(() => rentApi.summary({ branch_id: activeBranchId }),
    [activeBranchId], { enabled: can('rent.view') || can('invoices.view') })
  const residents = useApi(
    () => residentApi.list({ status: 'live', branch_id: activeBranchId, page_size: 200 }),
    [activeBranchId], { enabled: can('customers.view') })
  const openInvoices = useApi(
    () => (f.resident_id ? invoiceApi.list({ resident_id: f.resident_id, page_size: 50 })
      : Promise.resolve({ items: [] })),
    [f.resident_id], { enabled: open })
  const payments = useApi(
    () => paymentApi.list({ search, status, method, branch_id: activeBranchId,
      page, page_size: 25 }),
    [search, status, method, activeBranchId, page])

  const rows = payments.data?.items || []
  const pagination = payments.data?.pagination
  const s = summary.data
  const unpaid = (openInvoices.data?.items || []).filter(
    (i) => Number(i.balance) > 0 && i.status !== 'CANCELLED')
  const chosen = unpaid.find((i) => i.id === f.invoice_id)

  const openNew = () => {
    setF({ resident_id: '', invoice_id: '', amount: '', method: 'UPI',
      payment_date: today(), reference: '', notes: '', auto_verify: false })
    setOpen(true)
  }

  const save = async () => {
    if (!f.resident_id) return error('Choose a resident.')
    if (!(Number(f.amount) > 0)) return error('Enter an amount.')
    setBusy(true)
    try {
      const created = await paymentApi.create({
        resident_id: f.resident_id, invoice_id: f.invoice_id || null,
        amount: Number(f.amount), payment_date: f.payment_date || null,
        method: f.method, reference: f.reference || null, notes: f.notes || null,
        auto_verify: !!f.auto_verify,
      })
      success(`Payment ${created.payment_number} recorded`,
        created.status === 'PENDING' ? 'Awaiting verification.' : 'Verified.')
      setOpen(false)
      payments.reload(); summary.reload()
    } catch (err) { error('Could not record the payment', err.message) }
    finally { setBusy(false) }
  }

  const decide = async (p, approved) => {
    try {
      await paymentApi.verify(p.id, approved, null)
      success(approved ? 'Payment verified' : 'Payment rejected',
        approved ? 'The invoice balance has been updated.' : undefined)
      payments.reload(); summary.reload()
    } catch (err) { error('That did not work', err.message) }
  }

  const refund = async (p) => {
    try {
      await paymentApi.refund(p.id, 'Refunded from the payments screen')
      success('Payment refunded')
      payments.reload(); summary.reload()
    } catch (err) { error('Could not refund', err.message) }
  }

  const columns = [
    { key: 'payment_number', header: 'Payment',
      render: (p) => <div><p className="font-medium text-slate-900">{p.payment_number}</p>
        <p className="text-xs text-slate-500 truncate">{p.resident}</p></div> },
    { key: 'payment_date', header: 'Date',
      render: (p) => <span className="text-sm tnum text-slate-600">
        {dateFmt(p.payment_date)}</span> },
    { key: 'method', header: 'Method',
      render: (p) => <StatusBadge status={p.method.replace('_', ' ')} tone="slate" /> },
    { key: 'reference', header: 'Reference', sortable: false,
      render: (p) => <span className="text-xs text-slate-500 font-mono">
        {p.reference || '—'}</span> },
    { key: 'amount', header: 'Amount', align: 'right',
      render: (p) => <span className="tnum font-medium text-slate-900">{inr(p.amount)}</span> },
    { key: 'status', header: 'Status', render: (p) => <StatusBadge status={p.status} dot /> },
    { key: 'actions', header: '', sortable: false, align: 'right',
      render: (p) => (
        <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          {p.status === 'PENDING' && (
            <PermissionGuard perm="payments.verify">
              <IconButton icon={ShieldCheck} label="Verify" onClick={() => decide(p, true)} />
              <IconButton icon={ShieldX} label="Reject" tone="danger"
                onClick={() => decide(p, false)} />
            </PermissionGuard>
          )}
          {p.status === 'VERIFIED' && (
            <PermissionGuard perm="payments.refund">
              <IconButton icon={Undo2} label="Refund" tone="danger" onClick={() => refund(p)} />
            </PermissionGuard>
          )}
        </div>
      ) },
  ]

  return (
    <>
      <PageHeader title="Payments"
        subtitle="Money received, and whether it has been confirmed."
        actions={<PermissionGuard perm="payments.create">
          <Button variant="primary" icon={Plus} onClick={openNew}>Record payment</Button>
        </PermissionGuard>} />

      {s && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
          <StatCard label="Collected this month" value={inr(s.collected)}
            icon={IndianRupee} tone="emerald" sub={`${s.collection_rate}% of billed`} />
          <StatCard label="Outstanding" value={inr(s.outstanding)} tone="amber" />
          <StatCard label="Awaiting verification" value={num(s.unverified_payments)}
            tone={s.unverified_payments ? 'rose' : 'slate'}
            sub="not yet counted as paid" />
          <StatCard label="Overdue" value={inr(s.overdue)} tone="rose" />
        </div>
      )}

      <InlineAlert tone="info" className="mb-4">
        A payment does not reduce an invoice balance until it is verified. Recording
        one at the front desk is a claim; verifying it is the confirmation.
      </InlineAlert>

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={(v) => { setSearch(v); setPage(1) }}
            searchPlaceholder="Search payment number, reference or resident…"
            filters={[
              { key: 'status', label: 'Status', value: status,
                onChange: (v) => { setStatus(v); setPage(1) }, options: STATUSES },
              { key: 'method', label: 'Method', value: method,
                onChange: (v) => { setMethod(v); setPage(1) }, options: METHODS },
            ]} />
        </div>

        {payments.error ? (
          <InlineAlert tone="error" className="m-4">{payments.error.message}</InlineAlert>
        ) : payments.loading && !payments.data ? (
          <div className="p-4 space-y-2">{[0, 1, 2, 3].map((i) =>
            <Skeleton key={i} className="h-14" />)}</div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={25}
            mobileCard={(p) => (
              <div className="space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900">{p.payment_number}</p>
                    <p className="text-xs text-slate-500 truncate">{p.resident}</p>
                  </div>
                  <StatusBadge status={p.status} />
                </div>
                <div className="flex justify-between text-xs tnum">
                  <span className="text-slate-500">
                    {dateFmt(p.payment_date)} · {p.method.replace('_', ' ')}</span>
                  <span className="font-medium text-slate-900">{inr(p.amount)}</span>
                </div>
              </div>
            )}
            empty={<EmptyState icon={IndianRupee} title="No payments match"
              message="Clear the filters, or record the first one." />} />
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between">
            <p className="text-xs text-slate-500 tnum">
              Page {pagination.page} of {pagination.total_pages} · {pagination.total} payments
            </p>
            <div className="flex gap-2">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" disabled={page >= pagination.total_pages}
                onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} size="md" title="Record a payment"
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>Record payment</Button></>}>
        <div className="space-y-4">
          <FormField label="Resident" required>
            <Select value={f.resident_id || ''}
              onChange={(e) => setF({ ...f, resident_id: e.target.value, invoice_id: '' })}>
              <option value="">Choose…</option>
              {(residents.data?.items || []).map((r) => (
                <option key={r.id} value={r.id}>{r.full_name}</option>
              ))}
            </Select>
          </FormField>

          <FormField label="Against invoice"
            hint="Leave blank to record it without linking to an invoice.">
            <Select value={f.invoice_id || ''}
              onChange={(e) => {
                const inv = unpaid.find((i) => i.id === e.target.value)
                setF({ ...f, invoice_id: e.target.value,
                  amount: inv ? String(inv.balance) : f.amount })
              }}>
              <option value="">Not linked</option>
              {unpaid.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.invoice_number} — {inr(i.balance)} outstanding
                </option>
              ))}
            </Select>
          </FormField>

          <div className="grid sm:grid-cols-2 gap-4">
            <FormField label="Amount" required
              error={chosen && Number(f.amount) > Number(chosen.balance)
                ? `More than the ${inr(chosen.balance)} outstanding.` : undefined}>
              <Input inputMode="numeric" className="tnum" value={f.amount || ''}
                onChange={(e) => setF({ ...f, amount: e.target.value })} />
            </FormField>
            <FormField label="Method">
              <Select value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })}>
                {METHODS.map((m) => <option key={m} value={m}>{m.replace('_', ' ')}</option>)}
              </Select>
            </FormField>
            <FormField label="Date">
              <Input type="date" value={f.payment_date || ''}
                onChange={(e) => setF({ ...f, payment_date: e.target.value })} />
            </FormField>
            <FormField label="Reference" hint="UTR, cheque number or receipt.">
              <Input value={f.reference || ''}
                onChange={(e) => setF({ ...f, reference: e.target.value })} />
            </FormField>
          </div>

          <FormField label="Notes">
            <Textarea rows={2} value={f.notes || ''}
              onChange={(e) => setF({ ...f, notes: e.target.value })} />
          </FormField>

          <PermissionGuard perm="payments.verify">
            <Checkbox checked={!!f.auto_verify}
              onChange={(e) => setF({ ...f, auto_verify: e.target.checked })}
              label="Verify immediately"
              description="Only tick this if you have seen the money land." />
          </PermissionGuard>
        </div>
      </Modal>
    </>
  )
}
