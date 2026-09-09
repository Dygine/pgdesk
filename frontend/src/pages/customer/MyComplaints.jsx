import { useState } from 'react'
import { Plus, MessageSquareWarning } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { meApi } from '@/services/api/meApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, StatusBadge, EmptyState, Skeleton, InlineAlert,
  Modal, FormField, Input, Select, Textarea, StatCard,
} from '@/components/ui'
import { num, relative } from '@/lib/format'

const CATEGORIES = ['Maintenance', 'Electrical', 'Plumbing', 'Housekeeping', 'Food',
  'Internet', 'Security', 'Room', 'Payment', 'Other']
const TONE = { OPEN: 'amber', IN_PROGRESS: 'brand', WAITING: 'slate',
  RESOLVED: 'emerald', CLOSED: 'slate', REOPENED: 'rose' }

export default function MyComplaints() {
  const { success, error } = useToast()
  const { data, loading, error: failed, reload } = useApi(() => meApi.complaints(), [])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({ category: 'Maintenance', subject: '',
    description: '', priority: 'MEDIUM' })

  const submit = async () => {
    if (f.subject.trim().length < 3) return error('Describe the problem in the subject.')
    setBusy(true)
    try {
      const created = await meApi.raiseComplaint({
        category: f.category, subject: f.subject.trim(),
        description: f.description || null, priority: f.priority })
      success(`Complaint ${created.ticket_number} raised`, 'The staff have been notified.')
      setOpen(false)
      setF({ category: 'Maintenance', subject: '', description: '', priority: 'MEDIUM' })
      reload()
    } catch (err) { error('Could not raise the complaint', err.message) }
    finally { setBusy(false) }
  }

  const rows = data || []
  const openCount = rows.filter((c) => !['RESOLVED', 'CLOSED'].includes(c.status)).length

  return (
    <>
      <PageHeader title="My complaints"
        subtitle="Report something broken and follow what happens next."
        actions={<Button variant="primary" icon={Plus} onClick={() => setOpen(true)}>
          Raise a complaint</Button>} />

      {failed ? (
        <InlineAlert tone="error" title="Could not load">{failed.message}</InlineAlert>
      ) : loading && !data ? <Skeleton className="h-64" /> : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
            <StatCard label="Open" value={num(openCount)} icon={MessageSquareWarning}
              tone={openCount ? 'amber' : 'emerald'} />
            <StatCard label="Resolved"
              value={num(rows.filter((c) => c.status === 'RESOLVED').length)} tone="emerald" />
            <StatCard label="Total raised" value={num(rows.length)} tone="slate" />
            <StatCard label="Urgent"
              value={num(rows.filter((c) => c.priority === 'URGENT' &&
                !['RESOLVED', 'CLOSED'].includes(c.status)).length)} tone="rose" />
          </div>

          {rows.length === 0 ? (
            <Card><EmptyState icon={MessageSquareWarning} title="Nothing reported"
              message="If something in your room needs fixing, raise it here."
              action={<Button variant="primary" icon={Plus} onClick={() => setOpen(true)}>
                Raise a complaint</Button>} /></Card>
          ) : (
            <div className="space-y-3">
              {rows.map((c) => (
                <Card key={c.id}>
                  <div className="p-4 sm:p-5">
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900">{c.subject}</p>
                        <p className="text-2xs text-slate-500">
                          {c.ticket_number} · {c.category} · {relative(c.created_at)}
                        </p>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <StatusBadge status={c.priority}
                          tone={c.priority === 'URGENT' ? 'rose'
                            : c.priority === 'HIGH' ? 'amber' : 'slate'} />
                        <StatusBadge status={c.status.replace('_', ' ')}
                          tone={TONE[c.status]} dot />
                      </div>
                    </div>

                    {c.updates.length > 0 && (
                      <div className="mt-3 space-y-2 border-l-2 border-line pl-3">
                        {c.updates.map((u, i) => (
                          <div key={i}>
                            <p className="text-sm text-slate-700">{u.message}</p>
                            <p className="text-2xs text-slate-400">
                              {u.author} · {relative(u.created_at)}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}

                    {c.resolution && (
                      <InlineAlert tone="success" className="mt-3" title="Resolved">
                        {c.resolution}
                      </InlineAlert>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}

      <Modal open={open} onClose={() => setOpen(false)} size="sm" title="Raise a complaint"
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>Send</Button></>}>
        <div className="space-y-4">
          <FormField label="What is it about" required>
            <Select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
              {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </Select>
          </FormField>
          <FormField label="Subject" required>
            <Input value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })}
              placeholder="Tap leaking in the bathroom" />
          </FormField>
          <FormField label="Details">
            <Textarea rows={3} value={f.description}
              onChange={(e) => setF({ ...f, description: e.target.value })}
              placeholder="Since Monday morning, water pooling near the door." />
          </FormField>
          <FormField label="How urgent">
            <Select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
              {['LOW', 'MEDIUM', 'HIGH', 'URGENT'].map((p) => <option key={p}>{p}</option>)}
            </Select>
          </FormField>
        </div>
      </Modal>
    </>
  )
}
