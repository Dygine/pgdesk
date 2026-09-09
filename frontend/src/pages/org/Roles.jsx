import { useMemo, useState } from 'react'
import { Plus, ShieldCheck, Pencil, Trash2, Copy, Lock } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { roleApi, permissionApi } from '@/services/api/roleApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, StatCard, StatusBadge, EmptyState, Modal, FormField, Input,
  Textarea, Checkbox, IconButton, InlineAlert, Skeleton, ConfirmDialog,
} from '@/components/ui'
import { num } from '@/lib/format'

export default function Roles() {
  const { success, error } = useToast()
  const [modal, setModal] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})
  const [errs, setErrs] = useState({})

  const roles = useApi(() => roleApi.list(), [])
  const catalog = useApi(() => permissionApi.catalog(), [])

  const roleRows = roles.data || []
  const modules = catalog.data?.modules || []

  const openNew = () => {
    setF({ name: '', description: '', all_branches: false, permissions: [] })
    setErrs({}); setModal('new')
  }
  const openEdit = (r) => {
    setF({ ...r, permissions: [...r.permissions] })
    setErrs({}); setModal(r)
  }
  const duplicate = (r) => {
    setF({ name: `${r.name} (copy)`, description: r.description,
      all_branches: r.all_branches, permissions: [...r.permissions] })
    setErrs({}); setModal('new')
  }

  const has = (code) => f.permissions?.includes(code)
  const toggle = (code) => setF((x) => ({
    ...x,
    permissions: x.permissions.includes(code)
      ? x.permissions.filter((c) => c !== code) : [...x.permissions, code],
  }))
  const toggleModule = (m) => {
    const codes = m.permissions.map((p) => p.code)
    const all = codes.every((c) => f.permissions.includes(c))
    setF((x) => ({
      ...x,
      permissions: all
        ? x.permissions.filter((c) => !codes.includes(c))
        : [...new Set([...x.permissions, ...codes])],
    }))
  }

  const locked = modal !== 'new' && modal?.is_system_role

  const save = async () => {
    const e = {}
    if (!f.name?.trim()) e.name = 'Give the role a name.'
    if (!f.permissions?.length) e.permissions = 'Select at least one permission.'
    setErrs(e)
    if (Object.keys(e).length) return

    setBusy(true)
    try {
      if (modal === 'new') {
        await roleApi.create({
          name: f.name.trim(), description: f.description,
          all_branches: !!f.all_branches, permissions: f.permissions })
        success(`${f.name} created`)
      } else {
        await roleApi.update(modal.id, {
          name: f.name.trim(), description: f.description,
          all_branches: !!f.all_branches, permissions: f.permissions })
        success(`${f.name} updated`, 'Holders pick this up on their next request.')
      }
      setModal(null)
      roles.reload()
    } catch (err) {
      error('Could not save the role', err.message)
    } finally { setBusy(false) }
  }

  const remove = async () => {
    try {
      await roleApi.remove(confirm.id)
      success('Role deleted')
      roles.reload()
    } catch (err) { error('Could not delete', err.message) } finally { setConfirm(null) }
  }

  const totalPermissions = catalog.data?.count ?? 0

  return (
    <>
      <PageHeader title="Roles & permissions"
        subtitle="Build the roles your PG actually needs. The API enforces every one of them."
        actions={<PermissionGuard perm="roles.create">
          <Button variant="primary" icon={Plus} onClick={openNew}>Create role</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Roles" value={num(roleRows.length)} icon={ShieldCheck} tone="brand" />
        <StatCard label="Permissions available" value={num(totalPermissions)} tone="violet" />
        <StatCard label="Modules" value={num(modules.length)} tone="blue" />
        <StatCard label="People assigned"
          value={num(roleRows.reduce((a, r) => a + r.user_count, 0))} tone="emerald" />
      </div>

      <InlineAlert tone="info" className="mb-4">
        Permissions are read from the database on every request, so a change here takes
        effect on the holder's next action — not their next sign-in.
      </InlineAlert>

      {roles.error ? (
        <InlineAlert tone="error" title="Could not load roles">{roles.error.message}</InlineAlert>
      ) : roles.loading && !roles.data ? (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-44" />)}
        </div>
      ) : roleRows.length === 0 ? (
        <Card><EmptyState icon={ShieldCheck} title="No roles yet"
          message="Create one to start assigning staff." /></Card>
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {roleRows.map((r) => (
            <Card key={r.id} className="p-4">
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900 truncate">{r.name}</p>
                  <p className="text-xs text-slate-500 line-clamp-2">{r.description || '—'}</p>
                </div>
                {r.is_system_role && <StatusBadge status="System" tone="slate" />}
              </div>

              <div className="flex flex-wrap gap-1.5 my-3">
                <StatusBadge status={`${r.permissions.length} permissions`} tone="brand" />
                {r.all_branches && <StatusBadge status="All branches" tone="violet" />}
                <StatusBadge status={`${r.user_count} ${r.user_count === 1 ? 'user' : 'users'}`}
                  tone="slate" />
              </div>

              <div className="flex gap-1.5">
                <PermissionGuard perm="roles.edit">
                  <Button size="sm" icon={r.is_system_role ? Lock : Pencil} className="flex-1"
                    onClick={() => openEdit(r)}>
                    {r.is_system_role ? 'View' : 'Edit'}
                  </Button>
                </PermissionGuard>
                <PermissionGuard perm="roles.create">
                  <IconButton icon={Copy} label="Duplicate role" onClick={() => duplicate(r)} />
                </PermissionGuard>
                {!r.is_system_role && (
                  <PermissionGuard perm="roles.delete">
                    <IconButton icon={Trash2} label="Delete role" tone="danger"
                      onClick={() => setConfirm(r)} />
                  </PermissionGuard>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={!!modal} onClose={() => setModal(null)} size="lg"
        title={modal === 'new' ? 'Create a role' : locked ? `${f.name} (system role)` : `Edit ${f.name}`}
        subtitle={`${f.permissions?.length || 0} of ${totalPermissions} permissions selected`}
        footer={<><Button onClick={() => setModal(null)}>{locked ? 'Close' : 'Cancel'}</Button>
          {!locked && <Button variant="primary" loading={busy} onClick={save}>
            {modal === 'new' ? 'Create role' : 'Save role'}</Button>}</>}>
        <div className="space-y-5">
          {locked && (
            <InlineAlert tone="warn" title="This role cannot be changed">
              The owner role is what stops an organisation locking itself out of its own
              account. Duplicate it if you need a version you can trim.
            </InlineAlert>
          )}

          <div className="grid sm:grid-cols-2 gap-4">
            <FormField label="Role name" required error={errs.name}>
              <Input value={f.name || ''} onChange={(e) => setF({ ...f, name: e.target.value })}
                error={errs.name} disabled={locked} placeholder="Front Office" />
            </FormField>
            <FormField label="Description">
              <Input value={f.description || ''} disabled={locked}
                onChange={(e) => setF({ ...f, description: e.target.value })} />
            </FormField>
          </div>

          <Checkbox checked={!!f.all_branches} disabled={locked}
            onChange={(e) => setF({ ...f, all_branches: e.target.checked })}
            label="Sees every branch"
            description="Including branches created later. Leave off to assign branches per user." />

          <div>
            <div className="flex items-center justify-between mb-3 pb-2 border-b border-line">
              <p className="text-[13px] font-semibold text-slate-800">Permissions</p>
              {errs.permissions && <p className="text-xs text-rose-600">{errs.permissions}</p>}
            </div>

            {catalog.loading ? <Skeleton className="h-48" /> : (
              <div className="space-y-4 max-h-[46vh] overflow-y-auto pr-1">
                {modules.map((m) => {
                  const codes = m.permissions.map((p) => p.code)
                  const on = codes.filter((c) => has(c)).length
                  return (
                    <div key={m.key}>
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <button type="button" disabled={locked}
                          onClick={() => toggleModule(m)}
                          className="text-xs font-medium text-slate-800 hover:text-brand-800 disabled:hover:text-slate-800">
                          {m.label}
                        </button>
                        <span className="text-2xs text-slate-400 tnum">{on}/{codes.length}</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {m.permissions.map((p) => (
                          <button key={p.code} type="button" disabled={locked}
                            onClick={() => toggle(p.code)}
                            className={`px-2.5 py-1 rounded-md border text-xs transition-colors disabled:opacity-60 ${
                              has(p.code)
                                ? 'border-brand-300 bg-brand-50 text-brand-800'
                                : 'border-line bg-white text-slate-600 hover:bg-slate-50'}`}>
                            {p.action}
                          </button>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </Modal>

      <ConfirmDialog open={!!confirm} onClose={() => setConfirm(null)} tone="danger"
        title={`Delete ${confirm?.name}?`} confirmLabel="Delete role"
        message="Refused while anyone still holds it — move those users to another role first."
        onConfirm={remove} />
    </>
  )
}
