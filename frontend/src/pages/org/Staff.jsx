/**
 * Staff: the people who work at the PG.
 *
 * This used to be a one-line re-export of the Users page, on the reasoning that
 * staff and users were "the same people". They are not. Users are LOGINS - who
 * can open this app and what they can touch. Staff are the WORKFORCE - the cook,
 * the cleaner, the night guard - most of whom never sign in to anything, and
 * all of whom have a phone number, a shift and a salary that goes out monthly.
 *
 * Paying a salary here writes an ordinary "Salary" expense, so it shows up in
 * Expenses and in the P&L without a second ledger to keep in step.
 */
import { useState } from 'react'
import { Plus, UsersRound, Wallet, CalendarClock, Phone, CheckCircle2, Pencil } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { staffApi } from '@/services/api/staffApi'
import { branchApi } from '@/services/api/branchApi'
import { userApi } from '@/services/api/userApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard, Modal,
  FormField, Input, Select, Textarea, InlineAlert, Skeleton, Avatar,
} from '@/components/ui'
import { inr, num, dateFmt, today } from '@/lib/format'

const STATUS_LABEL = { ACTIVE: 'Working', ON_LEAVE: 'On leave', LEFT: 'Left' }
const STATUS_TONE = { ACTIVE: 'emerald', ON_LEAVE: 'amber', LEFT: 'slate' }
const METHODS = [['CASH', 'Cash'], ['UPI', 'UPI'], ['BANK_TRANSFER', 'Bank transfer']]
const thisMonth = () => today().slice(0, 7)

export default function Staff() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [designation, setDesignation] = useState('all')
  const [editing, setEditing] = useState(null)       // 'new' | staff row
  const [paying, setPaying] = useState(null)
  const [detail, setDetail] = useState(null)
  const [f, setF] = useState({})
  const [pay, setPay] = useState({})
  const [busy, setBusy] = useState(false)

  const branches = useApi(() => branchApi.list(), [],
    { enabled: can('branches.view'), initial: { items: [] } })
  const logins = useApi(() => userApi.list({ page_size: 200 }), [],
    { enabled: can('users.view'), initial: { items: [] } })
  const staff = useApi(
    () => staffApi.list({ search, status, designation, branch_id: activeBranchId }),
    [search, status, designation, activeBranchId])

  const rows = staff.data?.items || []
  const summary = staff.data?.summary
  const designations = staff.data?.designations || []
  const branchRows = branches.data?.items || []
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e?.target ? e.target.value : e }))

  const openNew = () => {
    setF({ full_name: '', designation: 'Cook', phone: '', shift: '', monthly_salary: '',
      joining_date: today(), branch_id: activeBranchId || branchRows[0]?.id || '',
      user_id: '', id_proof_reference: '', address: '', emergency_contact_name: '',
      emergency_contact_phone: '', notes: '' })
    setEditing('new')
  }
  const openEdit = (s) => {
    setF({ ...s, monthly_salary: s.monthly_salary || '', user_id: s.user_id || '' })
    setDetail(null)
    setEditing(s)
  }

  const save = async () => {
    if (!f.full_name?.trim()) return error('Enter a name.')
    if (!f.branch_id) return error('Choose the branch they work at.')
    const body = {
      full_name: f.full_name.trim(), designation: (f.designation || 'Other').trim(),
      phone: f.phone || null, shift: f.shift || null,
      monthly_salary: Number(f.monthly_salary) || 0, branch_id: f.branch_id,
      joining_date: f.joining_date || null, user_id: f.user_id || null,
      id_proof_reference: f.id_proof_reference || null, address: f.address || null,
      emergency_contact_name: f.emergency_contact_name || null,
      emergency_contact_phone: f.emergency_contact_phone || null, notes: f.notes || null,
    }
    setBusy(true)
    try {
      if (editing === 'new') {
        await staffApi.create(body)
        success(`${body.full_name} added`)
      } else {
        await staffApi.update(editing.id, { ...body, status: f.status })
        success(`${body.full_name} updated`)
      }
      setEditing(null)
      staff.reload()
    } catch (err) { error('Could not save', err.message) }
    finally { setBusy(false) }
  }

  const openPay = (s) => {
    setPay({ month: thisMonth(), amount: s.monthly_salary || '', paid_on: today(),
      payment_method: 'CASH', reference: '' })
    setPaying(s)
  }
  const confirmPay = async () => {
    if (!pay.month) return error('Choose the month this salary is for.')
    if (!(Number(pay.amount) > 0)) return error('Enter the amount paid.')
    setBusy(true)
    try {
      const r = await staffApi.paySalary(paying.id, {
        period: `${pay.month}-01`, amount: Number(pay.amount), paid_on: pay.paid_on || null,
        payment_method: pay.payment_method || null, reference: pay.reference || null })
      success('Salary recorded', `${r.expense_number} was added to expenses.`)
      setPaying(null)
      staff.reload()
    } catch (err) { error('Could not record the salary', err.message) }
    finally { setBusy(false) }
  }

  const openDetail = async (s) => {
    try { setDetail(await staffApi.get(s.id)) }
    catch (err) { error('Could not open', err.message) }
  }

  const salaryCell = (s) => {
    if (s.status === 'LEFT') return <span className="text-xs text-slate-400">—</span>
    if (s.paid_this_period) {
      return <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
        <CheckCircle2 size={14} /> Paid</span>
    }
    return (
      <PermissionGuard perm="expenses.create"
        fallback={<span className="text-xs text-amber-700">Not paid</span>}>
        <Button size="sm" icon={Wallet} onClick={(e) => { e.stopPropagation(); openPay(s) }}>
          Pay salary</Button>
      </PermissionGuard>
    )
  }

  const columns = [
    { key: 'full_name', header: 'Name', render: (s) => (
      <div className="flex items-center gap-2.5 min-w-0">
        <Avatar name={s.full_name} size="sm" />
        <div className="min-w-0">
          <p className="font-medium text-slate-900 truncate">{s.full_name}</p>
          <p className="text-xs text-slate-500 truncate">{s.designation}</p>
        </div>
      </div>) },
    { key: 'branch', header: 'Branch', render: (s) =>
      <span className="text-sm text-slate-700">{s.branch || '—'}</span> },
    { key: 'phone', header: 'Phone', sortable: false, render: (s) =>
      <span className="text-sm tnum text-slate-700">{s.phone || '—'}</span> },
    { key: 'shift', header: 'Shift', render: (s) =>
      <span className="text-sm text-slate-600">{s.shift || '—'}</span> },
    { key: 'monthly_salary', header: 'Salary', align: 'right', render: (s) =>
      <span className="tnum text-slate-800">{s.monthly_salary ? inr(s.monthly_salary) : '—'}</span> },
    { key: 'paid_this_period', header: 'This month', sortable: false, render: salaryCell },
    { key: 'status', header: 'Status', render: (s) =>
      <StatusBadge status={STATUS_LABEL[s.status]} tone={STATUS_TONE[s.status]} dot /> },
  ]

  return (
    <>
      <PageHeader title="Staff"
        subtitle="Everyone who works at your PG, and whether this month's salary has gone out. Who can sign in to the app is managed under Users & logins."
        actions={<PermissionGuard perm="staff.create">
          <Button variant="primary" icon={Plus} onClick={openNew}>Add staff member</Button>
        </PermissionGuard>} />

      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
          <StatCard label="Working" value={num(summary.active)} icon={UsersRound} tone="brand" />
          <StatCard label="On leave" value={num(summary.on_leave)} icon={CalendarClock}
            tone={summary.on_leave ? 'amber' : 'slate'} />
          <StatCard label="Monthly payroll" value={inr(summary.monthly_payroll)} tone="slate" />
          <StatCard label="Paid this month" value={inr(summary.paid_this_period)} icon={Wallet}
            tone={summary.unpaid_count ? 'amber' : 'emerald'}
            sub={summary.unpaid_count ? `${summary.unpaid_count} still to pay` : summary.active ? 'Everyone paid' : undefined} />
        </div>
      )}

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={setSearch}
            searchPlaceholder="Search name, phone or role…"
            filters={[
              { key: 'status', label: 'Status', value: status, onChange: setStatus,
                options: [{ value: 'ACTIVE', label: 'Working' },
                  { value: 'ON_LEAVE', label: 'On leave' }, { value: 'LEFT', label: 'Left' }] },
              { key: 'designation', label: 'Role', value: designation,
                onChange: setDesignation, options: designations },
            ]} />
        </div>
        {staff.error ? (
          <InlineAlert tone="error" className="m-4">{staff.error.message}</InlineAlert>
        ) : staff.loading && !staff.data ? (
          <div className="p-4 space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={25} onRowClick={openDetail}
            mobileCard={(s) => (
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <Avatar name={s.full_name} size="sm" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-900 truncate">{s.full_name}</p>
                      <p className="text-xs text-slate-500">{s.designation}{s.shift ? ` · ${s.shift}` : ''}</p>
                    </div>
                  </div>
                  <StatusBadge status={STATUS_LABEL[s.status]} tone={STATUS_TONE[s.status]} />
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs tnum text-slate-600">
                    {s.monthly_salary ? `${inr(s.monthly_salary)} / month` : 'No salary set'}</span>
                  {salaryCell(s)}
                </div>
              </div>
            )}
            empty={<EmptyState icon={UsersRound} title="No staff added yet"
              message="Add your cook, cleaners, guards and wardens - they do not need an app login."
              action={can('staff.create') && <Button variant="primary" icon={Plus} onClick={openNew}>
                Add staff member</Button>} />} />
        )}
      </Card>

      {/* ------------------------------------------------------ add / edit */}
      <Modal open={!!editing} onClose={() => setEditing(null)} size="lg"
        title={editing === 'new' ? 'Add a staff member' : `Edit ${editing?.full_name || ''}`}
        footer={<><Button onClick={() => setEditing(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>
            {editing === 'new' ? 'Add staff member' : 'Save changes'}</Button></>}>
        <div className="grid sm:grid-cols-2 gap-4">
          <FormField label="Name" required>
            <Input value={f.full_name || ''} onChange={set('full_name')} autoFocus />
          </FormField>
          <FormField label="Role" required hint="Pick one or type your own.">
            <Input list="staff-roles" value={f.designation || ''} onChange={set('designation')} />
            <datalist id="staff-roles">{designations.map((d) => <option key={d} value={d} />)}</datalist>
          </FormField>
          <FormField label="Phone">
            <Input value={f.phone || ''} inputMode="tel" onChange={set('phone')} />
          </FormField>
          <FormField label="Branch" required>
            <Select value={f.branch_id || ''} onChange={set('branch_id')}>
              <option value="">Choose…</option>
              {branchRows.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </Select>
          </FormField>
          <FormField label="Shift" hint="e.g. 6 am – 2 pm, or Night.">
            <Input value={f.shift || ''} onChange={set('shift')} />
          </FormField>
          <FormField label="Monthly salary">
            <Input inputMode="numeric" className="tnum" value={f.monthly_salary}
              onChange={set('monthly_salary')} placeholder="0" />
          </FormField>
          <FormField label="Joined on">
            <Input type="date" value={f.joining_date || ''} onChange={set('joining_date')} />
          </FormField>
          {editing !== 'new' && (
            <FormField label="Status">
              <Select value={f.status || 'ACTIVE'} onChange={set('status')}>
                <option value="ACTIVE">Working</option>
                <option value="ON_LEAVE">On leave</option>
                <option value="LEFT">Left the job</option>
              </Select>
            </FormField>
          )}
          <FormField label="ID proof" hint="Type and last digits, e.g. Aadhaar XXXX 4521.">
            <Input value={f.id_proof_reference || ''} onChange={set('id_proof_reference')} />
          </FormField>
          {can('users.view') && (
            <FormField label="App login" hint="Only if this person also signs in to PGDesk.">
              <Select value={f.user_id || ''} onChange={set('user_id')}>
                <option value="">No login</option>
                {(logins.data?.items || []).map((u) =>
                  <option key={u.id} value={u.id}>{u.name} · {u.email}</option>)}
              </Select>
            </FormField>
          )}
          <FormField label="Emergency contact">
            <Input value={f.emergency_contact_name || ''} onChange={set('emergency_contact_name')}
              placeholder="Name" />
          </FormField>
          <FormField label="Emergency phone">
            <Input value={f.emergency_contact_phone || ''} inputMode="tel"
              onChange={set('emergency_contact_phone')} />
          </FormField>
          <FormField label="Address" className="sm:col-span-2">
            <Input value={f.address || ''} onChange={set('address')} />
          </FormField>
          <FormField label="Notes" className="sm:col-span-2">
            <Textarea rows={2} value={f.notes || ''} onChange={set('notes')} />
          </FormField>
        </div>
      </Modal>

      {/* ---------------------------------------------------------- salary */}
      <Modal open={!!paying} onClose={() => setPaying(null)} size="sm"
        title={`Pay ${paying?.full_name || ''}`}
        subtitle="Recorded as a Salary expense, so it shows in Expenses and Accounts."
        footer={<><Button onClick={() => setPaying(null)}>Cancel</Button>
          <Button variant="primary" icon={Wallet} loading={busy} onClick={confirmPay}>
            Record {pay.amount ? inr(pay.amount) : 'salary'}</Button></>}>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="For the month" required className="col-span-2 sm:col-span-1">
            <Input type="month" value={pay.month || ''} max={thisMonth()}
              onChange={(e) => setPay({ ...pay, month: e.target.value })} />
          </FormField>
          <FormField label="Amount" required className="col-span-2 sm:col-span-1">
            <Input inputMode="numeric" className="tnum" value={pay.amount}
              onChange={(e) => setPay({ ...pay, amount: e.target.value })} />
          </FormField>
          <FormField label="Paid on">
            <Input type="date" value={pay.paid_on || ''} max={today()}
              onChange={(e) => setPay({ ...pay, paid_on: e.target.value })} />
          </FormField>
          <FormField label="Paid by">
            <Select value={pay.payment_method} onChange={(e) => setPay({ ...pay, payment_method: e.target.value })}>
              {METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </FormField>
          {pay.payment_method !== 'CASH' && (
            <FormField label="Reference / UTR" className="col-span-2">
              <Input value={pay.reference || ''} onChange={(e) => setPay({ ...pay, reference: e.target.value })} />
            </FormField>
          )}
        </div>
      </Modal>

      {/* ---------------------------------------------------------- detail */}
      <Modal open={!!detail} onClose={() => setDetail(null)} size="md"
        title={detail?.full_name} subtitle={detail ? `${detail.designation} · ${detail.branch || ''}` : ''}
        footer={<><Button onClick={() => setDetail(null)}>Close</Button>
          <PermissionGuard perm="staff.edit">
            <Button variant="primary" icon={Pencil} onClick={() => openEdit(detail)}>Edit</Button>
          </PermissionGuard></>}>
        {detail && (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              {[['Phone', detail.phone], ['Shift', detail.shift],
                ['Salary', detail.monthly_salary ? `${inr(detail.monthly_salary)} / month` : null],
                ['Joined', detail.joining_date && dateFmt(detail.joining_date)],
                ['Status', STATUS_LABEL[detail.status]], ['Left on', detail.left_on && dateFmt(detail.left_on)],
                ['ID proof', detail.id_proof_reference], ['App login', detail.login_email || 'None'],
                ['Emergency', [detail.emergency_contact_name, detail.emergency_contact_phone].filter(Boolean).join(' · ')],
              ].filter(([, v]) => v).map(([k, v]) => (
                <div key={k} className="min-w-0">
                  <p className="text-2xs text-slate-500">{k}</p>
                  <p className="text-slate-900 break-words">{v}</p>
                </div>
              ))}
            </div>
            {detail.phone && (
              <a href={`tel:${detail.phone}`}
                className="inline-flex items-center gap-1.5 text-sm text-brand-700 hover:underline">
                <Phone size={14} /> Call {detail.full_name.split(' ')[0]}</a>
            )}
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-2">Salary history</p>
              {detail.salaries.length === 0 ? (
                <p className="text-sm text-slate-500">No salary recorded yet.</p>
              ) : (
                <div className="divide-y divide-line rounded-lg border border-line">
                  {detail.salaries.map((x) => (
                    <div key={x.id} className="px-3 py-2 flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm text-slate-800">
                          {x.period ? new Date(`${x.period}T00:00:00`).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' }) : '—'}</p>
                        <p className="text-2xs text-slate-500 tnum">
                          {x.expense_number} · paid {dateFmt(x.paid_on)}{x.payment_method ? ` · ${x.payment_method.replace('_', ' ').toLowerCase()}` : ''}</p>
                      </div>
                      <span className="text-sm font-medium tnum text-slate-900">{inr(x.amount)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            {detail.notes && <p className="text-sm text-slate-600 whitespace-pre-line">{detail.notes}</p>}
          </div>
        )}
      </Modal>
    </>
  )
}
