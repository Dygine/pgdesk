import { useState } from 'react'
import { Plus, Users as UsersIcon, KeyRound, Pencil, UserX, Copy, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { userApi } from '@/services/api/userApi'
import { roleApi } from '@/services/api/roleApi'
import { branchApi } from '@/services/api/branchApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard, Modal,
  FormField, Input, Select, Checkbox, IconButton, InlineAlert, Skeleton,
  ConfirmDialog, ProgressBar, Avatar,
} from '@/components/ui'
import { num, relative } from '@/lib/format'

export default function Users() {
  const { can } = useAuth()
  const { success, error } = useToast()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [roleId, setRoleId] = useState('all')
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState(null)
  const [credentials, setCredentials] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})
  const [errs, setErrs] = useState({})

  /* A read-only viewer may hold staff.view without roles.view or branches.view.
     Firing those requests anyway would 403 in the console and tell them nothing,
     so each supporting fetch is gated on the permission it needs. The editor is
     hidden from these users regardless - only someone with users.create or
     users.edit ever needs the role and branch lists. */
  const roles = useApi(() => roleApi.list(), [], { enabled: can('roles.view'), initial: [] })
  const branches = useApi(() => branchApi.list(), [],
    { enabled: can('branches.view'), initial: { items: [] } })
  const plan = useApi(() => subscriptionApi.mine(), [],
    { enabled: can('dashboard.view'), initial: null })
  const users = useApi(
    () => userApi.list({ search, status, role_id: roleId, page, page_size: 25 }),
    [search, status, roleId, page],
  )

  const rows = users.data?.items || []
  const pagination = users.data?.pagination
  const roleRows = roles.data || []
  const branchRows = branches.data?.items || []

  const userLimit = plan.data?.limits?.users
  const usersUsed = plan.data?.usage?.users ?? 0
  const atLimit = userLimit != null && usersUsed >= userLimit

  const selectedRole = roleRows.find((r) => r.id === f.role_id)

  const openNew = () => {
    setF({ name: '', email: '', phone: '', employee_id: '', role_id: '', branch_ids: [] })
    setErrs({}); setModal('new')
  }
  const openEdit = (u) => {
    setF({ ...u, role_id: u.role?.id || u.roles?.[0]?.id || '',
      branch_ids: u.branches.map((b) => b.id) })
    setErrs({}); setModal(u)
  }
  const set = (k) => (e) => {
    setF((x) => ({ ...x, [k]: e?.target ? e.target.value : e }))
    setErrs((x) => ({ ...x, [k]: undefined }))
  }
  const toggleBranch = (id) => setF((x) => ({
    ...x,
    branch_ids: x.branch_ids.includes(id)
      ? x.branch_ids.filter((b) => b !== id) : [...x.branch_ids, id],
  }))

  const save = async () => {
    const e = {}
    if (!f.name?.trim()) e.name = 'Enter a name.'
    if (modal === 'new' && !/^\S+@\S+\.\S+$/.test(f.email || '')) e.email = 'Enter a valid email.'
    if (!f.role_id) e.role_id = 'Choose a role.'
    if (selectedRole && !selectedRole.all_branches && f.branch_ids.length === 0) {
      e.branch_ids = 'This role does not see every branch, so assign at least one.'
    }
    setErrs(e)
    if (Object.keys(e).length) return

    setBusy(true)
    try {
      if (modal === 'new') {
        const created = await userApi.create({
          name: f.name.trim(), email: f.email.trim().toLowerCase(), phone: f.phone || undefined,
          employee_id: f.employee_id || undefined, role_id: f.role_id, branch_ids: f.branch_ids,
        })
        setModal(null)
        setCredentials(created.credentials)
        success(`${created.name} created`)
      } else {
        await userApi.update(modal.id, {
          name: f.name.trim(), phone: f.phone, employee_id: f.employee_id,
          role_id: f.role_id, branch_ids: f.branch_ids, status: f.status,
        })
        setModal(null)
        success(`${f.name} updated`)
      }
      users.reload(); plan.reload()
    } catch (err) {
      error(modal === 'new' ? 'Could not create the user' : 'Could not save', err.message)
    } finally { setBusy(false) }
  }

  const deactivate = async () => {
    try {
      await userApi.deactivate(confirm.id)
      success(`${confirm.name} deactivated`)
      users.reload(); plan.reload()
    } catch (err) { error('Could not deactivate', err.message) } finally { setConfirm(null) }
  }

  const resetPassword = async (u) => {
    try {
      const c = await userApi.resetPassword(u.id)
      setCredentials(c)
      success('Temporary password issued')
      users.reload()
    } catch (err) { error('Could not reset the password', err.message) }
  }

  const columns = [
    { key: 'name', header: 'User',
      render: (u) => (
        <div className="flex items-center gap-2.5 min-w-0">
          <Avatar name={u.name} size="sm" />
          <div className="min-w-0">
            <p className="font-medium text-slate-900 truncate">{u.name}</p>
            <p className="text-xs text-slate-500 truncate">{u.email}</p>
          </div>
        </div>
      ) },
    { key: 'role', header: 'Role', sortable: false,
      render: (u) => (
        <div>
          <p className="text-sm text-slate-800">{u.role?.name || '—'}</p>
          <p className="text-2xs text-slate-500">{u.permissions.length} permissions</p>
        </div>
      ) },
    { key: 'branches', header: 'Branches', sortable: false,
      render: (u) => u.all_branches
        ? <StatusBadge status="All branches" tone="brand" />
        : <span className="text-sm text-slate-700">
            {u.branches.map((b) => b.code).join(', ') || '—'}</span> },
    { key: 'last_login_at', header: 'Last seen',
      render: (u) => <span className="text-xs text-slate-500">
        {u.last_login_at ? relative(u.last_login_at) : 'Never'}</span> },
    { key: 'status', header: 'Status',
      render: (u) => (
        <div className="flex items-center gap-1.5">
          <StatusBadge status={u.status} dot />
          {u.must_change_password && <StatusBadge status="Temp password" tone="amber" />}
        </div>
      ) },
    { key: 'actions', header: '', sortable: false, align: 'right',
      render: (u) => (
        <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          <PermissionGuard perm="users.edit">
            <IconButton icon={Pencil} label="Edit user" onClick={() => openEdit(u)} />
            <IconButton icon={KeyRound} label="Reset password" onClick={() => resetPassword(u)} />
          </PermissionGuard>
          {u.status !== 'DEACTIVATED' && (
            <PermissionGuard perm={['users.delete', 'users.deactivate']}>
              <IconButton icon={UserX} label="Deactivate" tone="danger"
                onClick={() => setConfirm(u)} />
            </PermissionGuard>
          )}
        </div>
      ) },
  ]

  return (
    <>
      <PageHeader title="Users & logins"
        subtitle="Who can sign in to PGDesk and what each role can do. The people who work here - including those with no login - are under Staff."
        actions={<PermissionGuard perm="users.create">
          <Button variant="primary" icon={Plus} onClick={openNew} disabled={atLimit}>Add user</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Users" value={`${usersUsed}${userLimit ? ` / ${userLimit}` : ''}`}
          icon={UsersIcon} tone={atLimit ? 'rose' : 'brand'}
          footer={userLimit ? <ProgressBar value={usersUsed} max={userLimit}
            tone={atLimit ? 'rose' : 'brand'} /> : undefined} />
        <StatCard label="Active"
          value={num(rows.filter((u) => u.status === 'ACTIVE').length)} tone="emerald" />
        <StatCard label="Roles in use" value={num(roleRows.length)} icon={ShieldCheck} tone="violet" />
        <StatCard label="Temporary passwords"
          value={num(rows.filter((u) => u.must_change_password).length)} tone="amber" />
      </div>

      {atLimit && (
        <InlineAlert tone="warn" className="mb-4" title="User limit reached">
          Your plan allows {userLimit} users. Deactivate someone or ask for an upgrade —
          the API refuses another regardless of what this screen shows.
        </InlineAlert>
      )}

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={(v) => { setSearch(v); setPage(1) }}
            searchPlaceholder="Search name, email or phone…"
            filters={[
              { key: 'role', label: 'Role', value: roleId,
                onChange: (v) => { setRoleId(v); setPage(1) },
                options: roleRows.map((r) => ({ value: r.id, label: r.name })) },
              { key: 'status', label: 'Status', value: status,
                onChange: (v) => { setStatus(v); setPage(1) },
                options: ['ACTIVE', 'SUSPENDED', 'DEACTIVATED', 'INVITED'] },
            ]} />
        </div>

        {users.error ? (
          <InlineAlert tone="error" className="m-4">{users.error.message}</InlineAlert>
        ) : users.loading && !users.data ? (
          <div className="p-4 space-y-2">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}
          </div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={25}
            mobileCard={(u) => (
              <div className="space-y-2">
                <div className="flex items-center gap-2.5">
                  <Avatar name={u.name} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-900 truncate">{u.name}</p>
                    <p className="text-xs text-slate-500 truncate">{u.role?.name || '—'}</p>
                  </div>
                  <StatusBadge status={u.status} />
                </div>
                <p className="text-2xs text-slate-500">
                  {u.all_branches ? 'All branches' : u.branches.map((b) => b.code).join(', ') || 'No branches'}
                  {' · '}{u.permissions.length} permissions
                </p>
              </div>
            )}
            empty={<EmptyState icon={UsersIcon} title="No users match"
              message="Clear the filters, or add your first staff member."
              action={<PermissionGuard perm="users.create">
                <Button variant="primary" icon={Plus} onClick={openNew}>Add user</Button>
              </PermissionGuard>} />} />
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between">
            <p className="text-xs text-slate-500 tnum">
              Page {pagination.page} of {pagination.total_pages} · {pagination.total} users
            </p>
            <div className="flex gap-2">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" disabled={page >= pagination.total_pages}
                onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      {/* ---------------------------------------------------------- editor */}
      <Modal open={!!modal} onClose={() => setModal(null)} size="md"
        title={modal === 'new' ? 'Add a user' : `Edit ${f.name}`}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>
            {modal === 'new' ? 'Create user' : 'Save changes'}</Button></>}>
        <div className="space-y-5">
          <div className="grid sm:grid-cols-2 gap-4">
            <FormField label="Full name" required error={errs.name} className="sm:col-span-2">
              <Input value={f.name || ''} onChange={set('name')} error={errs.name} />
            </FormField>
            <FormField label="Email" required error={errs.email}
              hint={modal === 'new' ? 'Becomes their sign-in address.' : undefined}>
              <Input type="email" value={f.email || ''} onChange={set('email')}
                error={errs.email} disabled={modal !== 'new'} />
            </FormField>
            <FormField label="Phone"><Input value={f.phone || ''} onChange={set('phone')} /></FormField>
            <FormField label="Employee ID">
              <Input value={f.employee_id || ''} onChange={set('employee_id')} />
            </FormField>
            {modal !== 'new' && (
              <FormField label="Status">
                <Select value={f.status || 'ACTIVE'} onChange={set('status')}>
                  {['ACTIVE', 'SUSPENDED', 'DEACTIVATED'].map((x) => <option key={x}>{x}</option>)}
                </Select>
              </FormField>
            )}
          </div>

          <FormField label="Role" required error={errs.role_id}>
            <Select value={f.role_id || ''} onChange={set('role_id')} error={errs.role_id}>
              <option value="">Choose a role…</option>
              {roleRows.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} — {r.permissions.length} permissions
                  {r.all_branches ? ' · all branches' : ''}
                </option>
              ))}
            </Select>
          </FormField>

          <div>
            <p className="text-[13px] font-medium text-slate-800 mb-2">Branch access</p>
            {selectedRole?.all_branches ? (
              <InlineAlert tone="info">
                This role sees every branch, including any created later, so individual
                assignments are not needed.
              </InlineAlert>
            ) : (
              <>
                <div className="grid sm:grid-cols-2 gap-2">
                  {branchRows.map((b) => (
                    <Checkbox key={b.id} checked={f.branch_ids?.includes(b.id) || false}
                      onChange={() => toggleBranch(b.id)}
                      label={b.name} description={`${b.code} · ${b.city || '—'}`} />
                  ))}
                </div>
                {errs.branch_ids && <p className="text-xs text-rose-600 mt-2">{errs.branch_ids}</p>}
              </>
            )}
          </div>

          {modal === 'new' && (
            <InlineAlert tone="info" icon={KeyRound}>
              A temporary password is generated and shown once. They must change it when
              they first sign in.
            </InlineAlert>
          )}
        </div>
      </Modal>

      {/* ----------------------------------------------------- credentials */}
      <Modal open={!!credentials} onClose={() => setCredentials(null)} size="sm"
        title="Temporary credentials" subtitle="Shown once — share them securely."
        footer={<Button variant="primary" onClick={() => setCredentials(null)}>Done</Button>}>
        {credentials && (
          <div className="space-y-4">
            <div className="rounded-lg border border-line bg-slate-50 p-4 space-y-2.5">
              {[['Name', credentials.name], ['Email', credentials.email],
                ['Password', credentials.temporary_password]].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-3">
                  <span className="text-xs text-slate-500">{k}</span>
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-sm text-slate-900 truncate">{v}</span>
                    <button type="button" aria-label={`Copy ${k}`}
                      onClick={() => { navigator.clipboard?.writeText(v); success(`${k} copied`) }}
                      className="text-slate-400 hover:text-slate-700 shrink-0"><Copy size={14} /></button>
                  </span>
                </div>
              ))}
            </div>
            <InlineAlert tone="warn">
              Stored only as a hash — it cannot be looked up later. Issue a new one if it is lost.
            </InlineAlert>
          </div>
        )}
      </Modal>

      <ConfirmDialog open={!!confirm} onClose={() => setConfirm(null)} tone="danger"
        title={`Deactivate ${confirm?.name}?`} confirmLabel="Deactivate"
        message="They can no longer sign in. Nothing they did is removed, and the account can be restored."
        onConfirm={deactivate} />
    </>
  )
}
