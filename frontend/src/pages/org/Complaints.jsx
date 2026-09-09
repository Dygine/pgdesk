import { useState } from 'react'
import { Plus, MessageSquareWarning, UserCheck, Send } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { complaintApi } from '@/services/api/complaintApi'
import { residentApi } from '@/services/api/residentApi'
import { userApi } from '@/services/api/userApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard, Modal,
  FormField, Input, Select, Textarea, Checkbox, InlineAlert, Skeleton,
} from '@/components/ui'
import { num, relative } from '@/lib/format'

const STATUSES = ['OPEN', 'IN_PROGRESS', 'WAITING', 'RESOLVED', 'CLOSED', 'REOPENED']
const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'URGENT']
const TONE = { OPEN: 'amber', IN_PROGRESS: 'brand', WAITING: 'slate',
  RESOLVED: 'emerald', CLOSED: 'slate', REOPENED: 'rose' }

export default function Complaints() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [priority, setPriority] = useState('all')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})
  const [work, setWork] = useState({})

  const categories = useApi(() => complaintApi.categories(), [], { initial: [] })
  const residents = useApi(
    () => residentApi.list({ status: 'live', branch_id: activeBranchId, page_size: 200 }),
    [activeBranchId], { enabled: can('customers.view') })
  const staff = useApi(() => userApi.list({ page_size: 100 }), [],
    { enabled: can('users.view') || can('staff.view') })
  const complaints = useApi(
    () => complaintApi.list({ search, status, priority, branch_id: activeBranchId,
      page, page_size: 25 }),
    [search, status, priority, activeBranchId, page])

  const rows = complaints.data?.items || []
  const pagination = complaints.data?.pagination

  const create = async () => {
    if (!f.subject?.trim()) return error('Describe the problem.')
    setBusy(true)
    try {
      await complaintApi.create({
        resident_id: f.resident_id || null, category: f.category || 'Other',
        subject: f.subject.trim(), description: f.description || null,
        priority: f.priority || 'MEDIUM' })
      success('Complaint raised')
      setOpen(false); setF({})
      complaints.reload()
    } catch (err) { error('Could not raise it', err.message) }
    finally { setBusy(false) }
  }

  const openDetail = async (c) => {
    try {
      const full = await complaintApi.get(c.id)
      setDetail(full)
      setWork({ status: full.status, assigned_to_id: full.assigned_to_id || '',
        message: '', is_internal: false, resolution: full.resolution || '' })
    } catch (err) { error('Could not open it', err.message) }
  }

  const saveWork = async () => {
    setBusy(true)
    try {
      const updated = await complaintApi.update(detail.id, {
        status: work.status, assigned_to_id: work.assigned_to_id || null,
        message: work.message || null, is_internal: !!work.is_internal,
        resolution: work.resolution || null })
      setDetail(updated)
      setWork((w) => ({ ...w, message: '' }))
      success('Complaint updated')
      complaints.reload()
    } catch (err) { error('Could not update', err.message) }
    finally { setBusy(false) }
  }

  const columns = [
    { key: 'ticket_number', header: 'Ticket',
      render: (c) => <div><p className="font-medium text-slate-900">{c.ticket_number}</p>
        <p className="text-xs text-slate-500 truncate">{c.subject}</p></div> },
    { key: 'category', header: 'Category',
      render: (c) => <StatusBadge status={c.category} tone="slate" /> },
    { key: 'resident', header: 'Raised by', sortable: false,
      render: (c) => <span className="text-sm text-slate-700">{c.resident || 'Staff'}</span> },
    { key: 'priority', header: 'Priority',
      render: (c) => <StatusBadge status={c.priority}
        tone={c.priority === 'URGENT' ? 'rose' : c.priority === 'HIGH' ? 'amber' : 'slate'} /> },
    { key: 'created_at', header: 'Age',
      render: (c) => <span className="text-xs text-slate-500">{relative(c.created_at)}</span> },
    { key: 'status', header: 'Status',
      render: (c) => <StatusBadge status={c.status.replace('_', ' ')} tone={TONE[c.status]} dot /> },
  ]

  const openCount = rows.filter((c) => !['RESOLVED', 'CLOSED'].includes(c.status)).length

  return (
    <>
      <PageHeader title="Complaints" subtitle="What is broken, who is on it and how old it is."
        actions={<PermissionGuard perm={['complaints.create', 'complaints.manage']}>
          <Button variant="primary" icon={Plus}
            onClick={() => { setF({ category: 'Maintenance', priority: 'MEDIUM' }); setOpen(true) }}>
            Log a complaint</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Open" value={num(openCount)} icon={MessageSquareWarning}
          tone={openCount ? 'amber' : 'emerald'} />
        <StatCard label="Urgent"
          value={num(rows.filter((c) => c.priority === 'URGENT' &&
            !['RESOLVED', 'CLOSED'].includes(c.status)).length)} tone="rose" />
        <StatCard label="Unassigned"
          value={num(rows.filter((c) => !c.assigned_to_id &&
            !['RESOLVED', 'CLOSED'].includes(c.status)).length)} tone="violet" />
        <StatCard label="Resolved"
          value={num(rows.filter((c) => ['RESOLVED', 'CLOSED'].includes(c.status)).length)}
          tone="emerald" />
      </div>

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={(v) => { setSearch(v); setPage(1) }}
            searchPlaceholder="Search ticket or subject…"
            filters={[
              { key: 'status', label: 'Status', value: status,
                onChange: (v) => { setStatus(v); setPage(1) }, options: STATUSES },
              { key: 'priority', label: 'Priority', value: priority,
                onChange: (v) => { setPriority(v); setPage(1) }, options: PRIORITIES },
            ]} />
        </div>

        {complaints.error ? (
          <InlineAlert tone="error" className="m-4">{complaints.error.message}</InlineAlert>
        ) : complaints.loading && !complaints.data ? (
          <div className="p-4 space-y-2">{[0, 1, 2, 3].map((i) =>
            <Skeleton key={i} className="h-14" />)}</div>
        ) : (
          <DataTable columns={columns} rows={rows} pageSize={25} onRowClick={openDetail}
            mobileCard={(c) => (
              <div className="space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">{c.subject}</p>
                    <p className="text-xs text-slate-500">
                      {c.ticket_number} · {c.category}</p>
                  </div>
                  <StatusBadge status={c.status.replace('_', ' ')} tone={TONE[c.status]} />
                </div>
                <p className="text-2xs text-slate-400">
                  {c.resident || 'Staff'} · {relative(c.created_at)}</p>
              </div>
            )}
            empty={<EmptyState icon={MessageSquareWarning} title="Nothing open"
              message="No complaints match these filters." />} />
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between">
            <p className="text-xs text-slate-500 tnum">
              Page {pagination.page} of {pagination.total_pages} · {pagination.total} tickets
            </p>
            <div className="flex gap-2">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" disabled={page >= pagination.total_pages}
                onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} size="sm" title="Log a complaint"
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={create}>Log it</Button></>}>
        <div className="space-y-4">
          <FormField label="Resident" hint="Leave blank for a general issue.">
            <Select value={f.resident_id || ''}
              onChange={(e) => setF({ ...f, resident_id: e.target.value })}>
              <option value="">Not resident-specific</option>
              {(residents.data?.items || []).map((r) => (
                <option key={r.id} value={r.id}>{r.full_name}</option>
              ))}
            </Select>
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Category">
              <Select value={f.category || 'Maintenance'}
                onChange={(e) => setF({ ...f, category: e.target.value })}>
                {(categories.data || []).map((c) => <option key={c}>{c}</option>)}
              </Select>
            </FormField>
            <FormField label="Priority">
              <Select value={f.priority || 'MEDIUM'}
                onChange={(e) => setF({ ...f, priority: e.target.value })}>
                {PRIORITIES.map((p) => <option key={p}>{p}</option>)}
              </Select>
            </FormField>
          </div>
          <FormField label="Subject" required>
            <Input value={f.subject || ''} onChange={(e) => setF({ ...f, subject: e.target.value })} />
          </FormField>
          <FormField label="Details">
            <Textarea rows={3} value={f.description || ''}
              onChange={(e) => setF({ ...f, description: e.target.value })} />
          </FormField>
        </div>
      </Modal>

      <Modal open={!!detail} onClose={() => setDetail(null)} size="md"
        title={detail?.subject} subtitle={`${detail?.ticket_number} · ${detail?.category}`}
        footer={<><Button onClick={() => setDetail(null)}>Close</Button>
          <PermissionGuard perm={['complaints.update', 'complaints.manage']}>
            <Button variant="primary" loading={busy} onClick={saveWork}>Save update</Button>
          </PermissionGuard></>}>
        {detail && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <StatusBadge status={detail.status.replace('_', ' ')} tone={TONE[detail.status]} dot />
              <StatusBadge status={detail.priority} tone="slate" />
              <span className="text-xs text-slate-500">
                {detail.resident || 'Staff'} · {relative(detail.created_at)}
              </span>
            </div>

            <div className="space-y-2 border-l-2 border-line pl-3 max-h-56 overflow-y-auto">
              {detail.updates?.map((u) => (
                <div key={u.id}>
                  <p className="text-sm text-slate-700">{u.message}</p>
                  <p className="text-2xs text-slate-400">
                    {u.author} · {relative(u.created_at)}
                    {u.is_internal ? ' · internal note' : ''}
                  </p>
                </div>
              ))}
            </div>

            <PermissionGuard perm={['complaints.update', 'complaints.assign', 'complaints.manage']}>
              <div className="space-y-3 pt-2 border-t border-line">
                <div className="grid sm:grid-cols-2 gap-3">
                  <FormField label="Status">
                    <Select value={work.status}
                      onChange={(e) => setWork({ ...work, status: e.target.value })}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
                    </Select>
                  </FormField>
                  <FormField label="Assign to">
                    <Select value={work.assigned_to_id}
                      onChange={(e) => setWork({ ...work, assigned_to_id: e.target.value })}>
                      <option value="">Nobody yet</option>
                      {(staff.data?.items || []).map((u) => (
                        <option key={u.id} value={u.id}>{u.name}</option>
                      ))}
                    </Select>
                  </FormField>
                </div>
                <FormField label="Add an update">
                  <Textarea rows={2} value={work.message}
                    onChange={(e) => setWork({ ...work, message: e.target.value })}
                    placeholder="Plumber visiting tomorrow morning." />
                </FormField>
                {['RESOLVED', 'CLOSED'].includes(work.status) && (
                  <FormField label="Resolution">
                    <Input value={work.resolution}
                      onChange={(e) => setWork({ ...work, resolution: e.target.value })} />
                  </FormField>
                )}
                <Checkbox checked={!!work.is_internal}
                  onChange={(e) => setWork({ ...work, is_internal: e.target.checked })}
                  label="Internal note"
                  description="Hidden from the resident's own view of this ticket." />
              </div>
            </PermissionGuard>
          </div>
        )}
      </Modal>
    </>
  )
}
