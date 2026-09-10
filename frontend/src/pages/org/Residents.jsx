import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Users, BedDouble, LogOut, ArrowLeftRight, Copy } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { residentApi } from '@/services/api/residentApi'
import { branchApi } from '@/services/api/branchApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard, PortalCredentials } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard, Modal,
  FormField, Input, Select, Checkbox, InlineAlert, Skeleton, ProgressBar, Avatar,
} from '@/components/ui'
import { inr, num, dateFmt } from '@/lib/format'

const STATUSES = ['ACTIVE', 'RESERVED', 'BOOKED', 'NOTICE', 'CHECKED_OUT', 'ENQUIRY']
const BLANK = {
  first_name: '', last_name: '', email: '', phone: '', gender: '',
  address: '', city: 'Bengaluru', state: 'Karnataka', pincode: '', occupation: '',
  emergency_contact_name: '', emergency_contact_phone: '', emergency_contact_relation: '',
  joining_date: '', expected_checkout_date: '', monthly_rent: '', security_deposit: '',
  rent_due_day: 5, notes: '', bed_id: '', create_portal_login: false,
}

export default function Residents() {
  const navigate = useNavigate()
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()

  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState(BLANK)
  const [errs, setErrs] = useState({})
  const [credentials, setCredentials] = useState(null)

  const branches = useApi(() => branchApi.list(), [], { enabled: can('branches.view') })
  const plan = useApi(() => subscriptionApi.mine(), [], { enabled: can('dashboard.view') })
  const beds = useApi(() => residentApi.availableBeds(activeBranchId), [activeBranchId],
    { enabled: open, initial: [] })
  const residents = useApi(
    () => residentApi.list({ search, status, branch_id: activeBranchId, page, page_size: 25 }),
    [search, status, activeBranchId, page])

  const rows = residents.data?.items || []
  const pagination = residents.data?.pagination
  const branchRows = branches.data?.items || []
  const limit = plan.data?.limits?.customers
  const used = plan.data?.usage?.customers ?? 0
  const atLimit = limit != null && used >= limit

  const set = (k) => (e) => {
    const v = e?.target ? (e.target.type === 'checkbox' ? e.target.checked : e.target.value) : e
    setF((x) => ({ ...x, [k]: v }))
    setErrs((x) => ({ ...x, [k]: undefined }))
  }

  const openNew = () => {
    setF({ ...BLANK, branch_id: activeBranchId || branchRows[0]?.id || '' })
    setErrs({}); setOpen(true)
  }

  const save = async () => {
    const e = {}
    if (!f.first_name.trim()) e.first_name = 'Enter a first name.'
    if (!/^[\d\s+\-()]{6,}$/.test(f.phone || '')) e.phone = 'Enter a valid phone number.'
    if (f.email && !/^\S+@\S+\.\S+$/.test(f.email)) e.email = 'Enter a valid email address.'
    if (f.create_portal_login && !f.email) e.email = 'A portal login needs an email address.'
    if (!f.branch_id) e.branch_id = 'Choose a branch.'
    setErrs(e)
    if (Object.keys(e).length) return

    setBusy(true)
    try {
      const created = await residentApi.create({
        branch_id: f.branch_id,
        first_name: f.first_name.trim(), last_name: f.last_name.trim() || null,
        full_name: `${f.first_name} ${f.last_name}`.trim(),
        email: f.email || null, phone: f.phone, gender: f.gender || null,
        address: f.address || null, city: f.city || null, state: f.state || null,
        pincode: f.pincode || null, occupation: f.occupation || null,
        emergency_contact_name: f.emergency_contact_name || null,
        emergency_contact_phone: f.emergency_contact_phone || null,
        emergency_contact_relation: f.emergency_contact_relation || null,
        joining_date: f.joining_date || null,
        expected_checkout_date: f.expected_checkout_date || null,
        monthly_rent: Number(f.monthly_rent) || 0,
        security_deposit: Number(f.security_deposit) || 0,
        rent_due_day: Number(f.rent_due_day) || 5,
        notes: f.notes || null,
        bed_id: f.bed_id || null,
        create_portal_login: !!f.create_portal_login,
      })
      setOpen(false)
      success(`${created.full_name} added`)
      if (created.credentials) {
        setCredentials({ ...created.credentials, name: created.full_name, residentId: created.id })
      }
      residents.reload(); plan.reload()
    } catch (err) {
      error('Could not add the resident', err.message)
      if (Object.keys(err.fieldErrors || {}).length) setErrs(err.fieldErrors)
    } finally { setBusy(false) }
  }

  const columns = [
    { key: 'full_name', header: 'Resident',
      render: (r) => (
        <div className="flex items-center gap-2.5 min-w-0">
          <Avatar name={r.full_name} size="sm" />
          <div className="min-w-0">
            <p className="font-medium text-slate-900 truncate">{r.full_name}</p>
            <p className="text-xs text-slate-500 truncate">{r.phone}</p>
          </div>
        </div>
      ) },
    { key: 'placement', header: 'Bed', sortable: false,
      render: (r) => r.placement?.bed
        ? <div><p className="text-sm text-slate-800">Room {r.placement.room}</p>
            <p className="text-2xs text-slate-500">{r.placement.branch_code} · bed {r.placement.bed_number}</p></div>
        : <StatusBadge status="Unassigned" tone="amber" /> },
    { key: 'monthly_rent', header: 'Rent', align: 'right',
      render: (r) => <span className="tnum font-medium text-slate-900">{inr(r.monthly_rent)}</span> },
    { key: 'joining_date', header: 'Joined',
      render: (r) => <span className="text-sm text-slate-600 tnum">
        {r.joining_date ? dateFmt(r.joining_date) : '—'}</span> },
    { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} dot /> },
    { key: 'actions', header: '', sortable: false, align: 'right',
      render: (r) => (
        <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          {!r.bed_id && r.status !== 'CHECKED_OUT' && (
            <PermissionGuard perm={['customers.assign_bed', 'beds.assign']}>
              <Button size="sm" icon={BedDouble}
                onClick={() => navigate(`/app/residents/${r.id}`)}>Assign</Button>
            </PermissionGuard>
          )}
          {r.bed_id && (
            <PermissionGuard perm="customers.transfer">
              <Button size="sm" icon={ArrowLeftRight}
                onClick={() => navigate('/app/transfer')}>Transfer</Button>
            </PermissionGuard>
          )}
          {r.status !== 'CHECKED_OUT' && (
            <PermissionGuard perm="customers.checkout">
              <Button size="sm" icon={LogOut}
                onClick={() => navigate('/app/checkout')}>Checkout</Button>
            </PermissionGuard>
          )}
        </div>
      ) },
  ]

  return (
    <>
      <PageHeader title="Residents"
        subtitle="Everyone living with you, where they sleep and what they pay."
        actions={<PermissionGuard perm="customers.create">
          <Button variant="primary" icon={Plus} onClick={openNew} disabled={atLimit}>
            Add resident
          </Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Residents" value={`${used}${limit ? ` / ${limit}` : ''}`}
          icon={Users} tone={atLimit ? 'rose' : 'brand'}
          footer={limit ? <ProgressBar value={used} max={limit}
            tone={atLimit ? 'rose' : 'brand'} /> : undefined} />
        <StatCard label="With a bed"
          value={num(rows.filter((r) => r.bed_id).length)} icon={BedDouble} tone="violet" />
        <StatCard label="Awaiting placement"
          value={num(rows.filter((r) => !r.bed_id && r.status !== 'CHECKED_OUT').length)}
          tone="amber" />
        <StatCard label="Monthly rent roll"
          value={inr(rows.filter((r) => r.status === 'ACTIVE')
            .reduce((a, r) => a + Number(r.monthly_rent || 0), 0))} tone="emerald" />
      </div>

      {atLimit && (
        <InlineAlert tone="warn" className="mb-4" title="Resident limit reached">
          Your plan allows {limit} residents. The API refuses another regardless of what
          this screen shows — check someone out or ask for an upgrade.
        </InlineAlert>
      )}

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={(v) => { setSearch(v); setPage(1) }}
            searchPlaceholder="Search name, phone or email…"
            filters={[{ key: 'status', label: 'Status', value: status,
              onChange: (v) => { setStatus(v); setPage(1) }, options: STATUSES }]} />
        </div>

        {residents.error ? (
          <InlineAlert tone="error" className="m-4">{residents.error.message}</InlineAlert>
        ) : residents.loading && !residents.data ? (
          <div className="p-4 space-y-2">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}
          </div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={25}
            onRowClick={(r) => navigate(`/app/residents/${r.id}`)}
            mobileCard={(r) => (
              <div className="space-y-2">
                <div className="flex items-center gap-2.5">
                  <Avatar name={r.full_name} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-900 truncate">{r.full_name}</p>
                    <p className="text-xs text-slate-500 truncate">
                      {r.placement?.room ? `Room ${r.placement.room} · bed ${r.placement.bed_number}`
                        : 'No bed assigned'}
                    </p>
                  </div>
                  <StatusBadge status={r.status} />
                </div>
                <p className="text-xs text-slate-500 tnum">
                  {inr(r.monthly_rent)} / month · {r.phone}
                </p>
              </div>
            )}
            empty={<EmptyState icon={Users} title="No residents match"
              message="Clear the filters, or add your first resident."
              action={<PermissionGuard perm="customers.create">
                <Button variant="primary" icon={Plus} onClick={openNew}>Add resident</Button>
              </PermissionGuard>} />} />
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between">
            <p className="text-xs text-slate-500 tnum">
              Page {pagination.page} of {pagination.total_pages} · {pagination.total} residents
            </p>
            <div className="flex gap-2">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" disabled={page >= pagination.total_pages}
                onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} size="lg" title="Add a resident"
        subtitle="A bed can be assigned now or later."
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>Add resident</Button></>}>
        <div className="space-y-5">
          <div className="grid sm:grid-cols-2 gap-4">
            <FormField label="First name" required error={errs.first_name}>
              <Input value={f.first_name} onChange={set('first_name')} error={errs.first_name} />
            </FormField>
            <FormField label="Last name">
              <Input value={f.last_name} onChange={set('last_name')} />
            </FormField>
            <FormField label="Phone" required error={errs.phone}>
              <Input value={f.phone} onChange={set('phone')} error={errs.phone}
                placeholder="+91 98765 43210" />
            </FormField>
            <FormField label="Email" required={!!f.create_portal_login} error={errs.email}
              hint={f.create_portal_login ? 'This becomes their sign-in ID for the app.'
                : 'Needed if they will use the app.'}>
              <Input type="email" value={f.email} onChange={set('email')} error={errs.email} />
            </FormField>
            <FormField label="Branch" required error={errs.branch_id}>
              <Select value={f.branch_id || ''} onChange={set('branch_id')} error={errs.branch_id}>
                <option value="">Choose…</option>
                {branchRows.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </Select>
            </FormField>
            <FormField label="Gender">
              <Select value={f.gender} onChange={set('gender')}>
                <option value="">Not specified</option>
                {['Male', 'Female', 'Other'].map((x) => <option key={x}>{x}</option>)}
              </Select>
            </FormField>
          </div>

          <div className="rounded-lg border border-line bg-slate-50/60 px-3.5 py-3">
            <Checkbox checked={f.create_portal_login} onChange={set('create_portal_login')}
              label="Give them app access now"
              description="You get a sign-in QR (works for 30 minutes) and a temporary password. You can also do this later from their profile." />
          </div>

          <div>
            <p className="text-[13px] font-semibold text-slate-800 mb-3 pb-2 border-b border-line">
              Bed and money
            </p>
            <div className="grid sm:grid-cols-2 gap-4">
              <FormField label="Bed" className="sm:col-span-2"
                hint="Only beds that are free right now are listed.">
                <Select value={f.bed_id} onChange={set('bed_id')}>
                  <option value="">Assign later</option>
                  {(beds.data || []).map((b) => (
                    <option key={b.id} value={b.id}>{b.label} — {inr(b.rent_amount)}</option>
                  ))}
                </Select>
              </FormField>
              <FormField label="Monthly rent" hint="Taken from the bed if left blank.">
                <Input inputMode="numeric" className="tnum" value={f.monthly_rent}
                  onChange={set('monthly_rent')} />
              </FormField>
              <FormField label="Security deposit">
                <Input inputMode="numeric" className="tnum" value={f.security_deposit}
                  onChange={set('security_deposit')} />
              </FormField>
              <FormField label="Joining date">
                <Input type="date" value={f.joining_date} onChange={set('joining_date')} />
              </FormField>
              <FormField label="Rent due day" hint="Day of the month, 1–28.">
                <Input inputMode="numeric" className="tnum" value={f.rent_due_day}
                  onChange={set('rent_due_day')} />
              </FormField>
            </div>
          </div>

          <div>
            <p className="text-[13px] font-semibold text-slate-800 mb-3 pb-2 border-b border-line">
              Emergency contact
            </p>
            <div className="grid sm:grid-cols-3 gap-4">
              <FormField label="Name">
                <Input value={f.emergency_contact_name} onChange={set('emergency_contact_name')} />
              </FormField>
              <FormField label="Phone">
                <Input value={f.emergency_contact_phone} onChange={set('emergency_contact_phone')} />
              </FormField>
              <FormField label="Relation">
                <Input value={f.emergency_contact_relation}
                  onChange={set('emergency_contact_relation')} placeholder="Father" />
              </FormField>
            </div>
          </div>

        </div>
      </Modal>

      <PortalCredentials open={!!credentials} onClose={() => setCredentials(null)}
        name={credentials?.name} credentials={credentials}
        onRenew={async (prev) => {
          const data = await residentApi.loginCode(prev.residentId)
          return { ...prev, ...data.credentials }
        }} />
    </>
  )
}
