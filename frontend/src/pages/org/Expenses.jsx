import { useState } from 'react'
import { Plus, Wallet, Trash2, Pencil } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { expenseApi } from '@/services/api/expenseApi'
import { branchApi } from '@/services/api/branchApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard,
  Modal, FormField, Input, Select, Textarea, InlineAlert, Skeleton, IconButton,
  ConfirmDialog,
} from '@/components/ui'
import { ChartCard, HBarChart } from '@/components/charts/Charts'
import { inr, num, dateFmt, today } from '@/lib/format'

export default function Expenses() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})

  const summary = useApi(() => expenseApi.summary(activeBranchId), [activeBranchId])
  const branches = useApi(() => branchApi.list(), [], { enabled: can('branches.view') })
  const expenses = useApi(
    () => expenseApi.list({ search, category, branch_id: activeBranchId, page, page_size: 25 }),
    [search, category, activeBranchId, page])

  const rows = expenses.data?.items || []
  const pagination = expenses.data?.pagination
  const s = summary.data
  const categories = s?.categories || []

  const openNew = () => {
    setF({ branch_id: activeBranchId || branches.data?.items?.[0]?.id || '',
      category: 'Maintenance', amount: '', spent_on: today(), vendor: '',
      payment_method: 'UPI', reference: '', description: '' })
    setModal('new')
  }
  const openEdit = (e) => { setF({ ...e }); setModal(e) }

  const save = async () => {
    if (!(Number(f.amount) > 0)) return error('Enter an amount.')
    setBusy(true)
    try {
      if (modal === 'new') {
        await expenseApi.create({ ...f, amount: Number(f.amount) })
        success('Expense recorded')
      } else {
        await expenseApi.update(modal.id, {
          category: f.category, amount: Number(f.amount), spent_on: f.spent_on,
          vendor: f.vendor, payment_method: f.payment_method,
          reference: f.reference, description: f.description })
        success('Expense updated')
      }
      setModal(null)
      expenses.reload(); summary.reload()
    } catch (err) { error('That did not work', err.message) }
    finally { setBusy(false) }
  }

  const remove = async () => {
    try {
      await expenseApi.remove(confirm.id)
      success('Expense deleted')
      expenses.reload(); summary.reload()
    } catch (err) { error('Could not delete', err.message) }
    finally { setConfirm(null) }
  }

  const columns = [
    { key: 'expense_number', header: 'Reference',
      render: (e) => <div><p className="font-medium text-slate-900">{e.expense_number}</p>
        <p className="text-xs text-slate-500 truncate">{e.vendor || '—'}</p></div> },
    { key: 'category', header: 'Category',
      render: (e) => <StatusBadge status={e.category} tone="slate" /> },
    { key: 'spent_on', header: 'Date',
      render: (e) => <span className="text-sm tnum text-slate-600">{dateFmt(e.spent_on)}</span> },
    { key: 'payment_method', header: 'Paid by', sortable: false,
      render: (e) => <span className="text-sm text-slate-600">
        {(e.payment_method || '—').replace('_', ' ')}</span> },
    { key: 'amount', header: 'Amount', align: 'right',
      render: (e) => <span className="tnum font-medium text-slate-900">{inr(e.amount)}</span> },
    { key: 'actions', header: '', sortable: false, align: 'right',
      render: (e) => (
        <div className="flex justify-end gap-1.5" onClick={(ev) => ev.stopPropagation()}>
          <PermissionGuard perm="expenses.edit">
            <IconButton icon={Pencil} label="Edit" onClick={() => openEdit(e)} />
          </PermissionGuard>
          <PermissionGuard perm="expenses.delete">
            <IconButton icon={Trash2} label="Delete" tone="danger" onClick={() => setConfirm(e)} />
          </PermissionGuard>
        </div>
      ) },
  ]

  return (
    <>
      <PageHeader title="Expenses" subtitle="What the PG spends, and on what."
        actions={<PermissionGuard perm="expenses.create">
          <Button variant="primary" icon={Plus} onClick={openNew}>Record expense</Button>
        </PermissionGuard>} />

      {s && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
          <StatCard label="Today" value={inr(s.today)} icon={Wallet} tone="slate" />
          <StatCard label="This month" value={inr(s.this_month)} tone="brand" />
          <StatCard label="This year" value={inr(s.this_year)} tone="violet" />
          <StatCard label="Categories in use" value={num(s.by_category.length)} tone="emerald" />
        </div>
      )}

      {s?.by_category?.length > 0 && (
        <ChartCard title="This month by category" subtitle="Largest first" className="mb-4">
          <HBarChart color="#373DA6" valueFormat={inr}
            data={s.by_category.map((c) => ({ label: c.category, value: c.amount }))} />
        </ChartCard>
      )}

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={(v) => { setSearch(v); setPage(1) }}
            searchPlaceholder="Search vendor, reference or note…"
            filters={[{ key: 'category', label: 'Category', value: category,
              onChange: (v) => { setCategory(v); setPage(1) }, options: categories }]} />
        </div>

        {expenses.error ? (
          <InlineAlert tone="error" className="m-4">{expenses.error.message}</InlineAlert>
        ) : expenses.loading && !expenses.data ? (
          <div className="p-4 space-y-2">{[0, 1, 2].map((i) =>
            <Skeleton key={i} className="h-14" />)}</div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={25}
            mobileCard={(e) => (
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900 truncate">
                    {e.vendor || e.category}</p>
                  <p className="text-xs text-slate-500 tnum">
                    {e.category} · {dateFmt(e.spent_on)}</p>
                </div>
                <p className="text-sm font-semibold text-slate-900 tnum shrink-0">
                  {inr(e.amount)}</p>
              </div>
            )}
            empty={<EmptyState icon={Wallet} title="No expenses match"
              message="Clear the filters, or record the first one." />} />
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between">
            <p className="text-xs text-slate-500 tnum">
              Page {pagination.page} of {pagination.total_pages} · {pagination.total} entries
            </p>
            <div className="flex gap-2">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" disabled={page >= pagination.total_pages}
                onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      <Modal open={!!modal} onClose={() => setModal(null)} size="sm"
        title={modal === 'new' ? 'Record an expense' : 'Edit expense'}
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
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Category" required>
              <Select value={f.category || ''}
                onChange={(e) => setF({ ...f, category: e.target.value })}>
                {categories.map((c) => <option key={c}>{c}</option>)}
              </Select>
            </FormField>
            <FormField label="Amount" required>
              <Input inputMode="numeric" className="tnum" value={f.amount ?? ''}
                onChange={(e) => setF({ ...f, amount: e.target.value })} />
            </FormField>
            <FormField label="Date">
              <Input type="date" value={f.spent_on || ''}
                onChange={(e) => setF({ ...f, spent_on: e.target.value })} />
            </FormField>
            <FormField label="Paid by">
              <Select value={f.payment_method || 'UPI'}
                onChange={(e) => setF({ ...f, payment_method: e.target.value })}>
                {['CASH', 'UPI', 'BANK_TRANSFER', 'CARD', 'CHEQUE'].map((m) =>
                  <option key={m} value={m}>{m.replace('_', ' ')}</option>)}
              </Select>
            </FormField>
          </div>
          <FormField label="Vendor">
            <Input value={f.vendor || ''} onChange={(e) => setF({ ...f, vendor: e.target.value })} />
          </FormField>
          <FormField label="Reference" hint="Bill number or UTR.">
            <Input value={f.reference || ''}
              onChange={(e) => setF({ ...f, reference: e.target.value })} />
          </FormField>
          <FormField label="Description">
            <Textarea rows={2} value={f.description || ''}
              onChange={(e) => setF({ ...f, description: e.target.value })} />
          </FormField>
        </div>
      </Modal>

      <ConfirmDialog open={!!confirm} onClose={() => setConfirm(null)} tone="danger"
        title={`Delete ${confirm?.expense_number}?`} confirmLabel="Delete"
        message="This removes the entry from your expense reports."
        onConfirm={remove} />
    </>
  )
}
