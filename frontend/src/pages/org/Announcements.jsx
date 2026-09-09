import { useState } from 'react'
import { Plus, Megaphone, Pencil, Trash2 } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { announcementApi } from '@/services/api/announcementApi'
import { branchApi } from '@/services/api/branchApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, StatusBadge, FilterBar, EmptyState, StatCard, Modal, FormField,
  Input, Select, Textarea, InlineAlert, Skeleton, IconButton, ConfirmDialog,
} from '@/components/ui'
import { num, dateFmt, relative, today } from '@/lib/format'

const AUDIENCES = ['ALL', 'RESIDENTS', 'STAFF', 'BRANCH']

export default function Announcements() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [status, setStatus] = useState('all')
  const [modal, setModal] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})

  const branches = useApi(() => branchApi.list(), [], { enabled: can('branches.view') })
  const list = useApi(() => announcementApi.list({ status, page_size: 50 }), [status])
  const rows = list.data?.items || []

  const openNew = () => {
    setF({ title: '', message: '', audience: 'ALL', priority: 'MEDIUM',
      status: 'PUBLISHED', branch_id: '', starts_on: today(), ends_on: '' })
    setModal('new')
  }
  const openEdit = (a) => { setF({ ...a, branch_id: a.branch_id || '' }); setModal(a) }

  const save = async () => {
    if (!f.title?.trim() || !f.message?.trim()) {
      return error('A title and a message are both needed.')
    }
    setBusy(true)
    try {
      const body = {
        title: f.title.trim(), message: f.message.trim(), audience: f.audience,
        priority: f.priority, status: f.status,
        branch_id: f.branch_id || null,
        starts_on: f.starts_on || null, ends_on: f.ends_on || null }
      if (modal === 'new') {
        await announcementApi.create(body)
        success('Announcement published',
          f.status === 'PUBLISHED' ? 'Everyone in the audience has been notified.' : undefined)
      } else {
        await announcementApi.update(modal.id, body)
        success('Announcement updated')
      }
      setModal(null)
      list.reload()
    } catch (err) { error('That did not work', err.message) }
    finally { setBusy(false) }
  }

  const remove = async () => {
    try {
      await announcementApi.remove(confirm.id)
      success('Announcement deleted')
      list.reload()
    } catch (err) { error('Could not delete', err.message) }
    finally { setConfirm(null) }
  }

  return (
    <>
      <PageHeader title="Announcements" subtitle="Notices sent to residents and staff."
        actions={<PermissionGuard perm="announcements.create">
          <Button variant="primary" icon={Plus} onClick={openNew}>New announcement</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Published"
          value={num(rows.filter((a) => a.status === 'PUBLISHED').length)}
          icon={Megaphone} tone="brand" />
        <StatCard label="Drafts"
          value={num(rows.filter((a) => a.status === 'DRAFT').length)} tone="amber" />
        <StatCard label="High priority"
          value={num(rows.filter((a) => ['HIGH', 'URGENT'].includes(a.priority)).length)}
          tone="rose" />
        <StatCard label="Total" value={num(rows.length)} tone="slate" />
      </div>

      <InlineAlert tone="info" className="mb-4">
        Publishing writes one notification per recipient, so each person can mark it
        read without affecting anyone else.
      </InlineAlert>

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar filters={[{ key: 'status', label: 'Status', value: status,
            onChange: setStatus, options: ['PUBLISHED', 'DRAFT', 'ARCHIVED'] }]} />
        </div>

        {list.error ? (
          <InlineAlert tone="error" className="m-4">{list.error.message}</InlineAlert>
        ) : list.loading && !list.data ? (
          <div className="p-4 space-y-2">{[0, 1, 2].map((i) =>
            <Skeleton key={i} className="h-20" />)}</div>
        ) : rows.length === 0 ? (
          <EmptyState icon={Megaphone} title="Nothing announced"
            message="Tell residents about maintenance, rent reminders or events." />
        ) : (
          <div className="divide-y divide-line">
            {rows.map((a) => (
              <div key={a.id} className="p-4 sm:p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-900">{a.title}</p>
                    <p className="text-sm text-slate-600 mt-1">{a.message}</p>
                    <p className="text-2xs text-slate-400 mt-1.5 tnum">
                      {relative(a.created_at)}
                      {a.starts_on ? ` · from ${dateFmt(a.starts_on)}` : ''}
                      {a.ends_on ? ` to ${dateFmt(a.ends_on)}` : ''}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1.5 shrink-0">
                    <StatusBadge status={a.audience} tone="slate" />
                    <StatusBadge status={a.priority}
                      tone={['HIGH', 'URGENT'].includes(a.priority) ? 'rose' : 'slate'} />
                    <StatusBadge status={a.status}
                      tone={a.status === 'PUBLISHED' ? 'emerald' : 'amber'} dot />
                  </div>
                </div>
                <div className="flex gap-1.5 mt-3">
                  <PermissionGuard perm="announcements.edit">
                    <IconButton icon={Pencil} label="Edit" onClick={() => openEdit(a)} />
                  </PermissionGuard>
                  <PermissionGuard perm="announcements.delete">
                    <IconButton icon={Trash2} label="Delete" tone="danger"
                      onClick={() => setConfirm(a)} />
                  </PermissionGuard>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Modal open={!!modal} onClose={() => setModal(null)} size="sm"
        title={modal === 'new' ? 'New announcement' : 'Edit announcement'}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>Save</Button></>}>
        <div className="space-y-4">
          <FormField label="Title" required>
            <Input value={f.title || ''} onChange={(e) => setF({ ...f, title: e.target.value })} />
          </FormField>
          <FormField label="Message" required>
            <Textarea rows={4} value={f.message || ''}
              onChange={(e) => setF({ ...f, message: e.target.value })} />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Audience">
              <Select value={f.audience || 'ALL'}
                onChange={(e) => setF({ ...f, audience: e.target.value })}>
                {AUDIENCES.map((a) => <option key={a}>{a}</option>)}
              </Select>
            </FormField>
            <FormField label="Priority">
              <Select value={f.priority || 'MEDIUM'}
                onChange={(e) => setF({ ...f, priority: e.target.value })}>
                {['LOW', 'MEDIUM', 'HIGH', 'URGENT'].map((p) => <option key={p}>{p}</option>)}
              </Select>
            </FormField>
          </div>
          {f.audience === 'BRANCH' && (
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
            <FormField label="From">
              <Input type="date" value={f.starts_on || ''}
                onChange={(e) => setF({ ...f, starts_on: e.target.value })} />
            </FormField>
            <FormField label="Until" hint="Blank means no end date.">
              <Input type="date" value={f.ends_on || ''}
                onChange={(e) => setF({ ...f, ends_on: e.target.value })} />
            </FormField>
          </div>
          <FormField label="Status">
            <Select value={f.status || 'PUBLISHED'}
              onChange={(e) => setF({ ...f, status: e.target.value })}>
              {['PUBLISHED', 'DRAFT', 'ARCHIVED'].map((s) => <option key={s}>{s}</option>)}
            </Select>
          </FormField>
        </div>
      </Modal>

      <ConfirmDialog open={!!confirm} onClose={() => setConfirm(null)} tone="danger"
        title={`Delete "${confirm?.title}"?`} confirmLabel="Delete"
        message="Notifications already sent are not withdrawn."
        onConfirm={remove} />
    </>
  )
}
