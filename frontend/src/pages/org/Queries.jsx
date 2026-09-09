import { useState } from 'react'
import { MessageCircleQuestion, Send, Plus } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { queryApi } from '@/services/api/queryApi'
import { residentApi } from '@/services/api/residentApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, DataTable, StatusBadge, FilterBar, EmptyState, StatCard, Modal,
  FormField, Input, Select, Textarea, Checkbox, InlineAlert, Skeleton,
} from '@/components/ui'
import { num, relative } from '@/lib/format'

const TONE = { OPEN: 'amber', ANSWERED: 'emerald', CLOSED: 'slate' }

export default function Queries() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [detail, setDetail] = useState(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [reply, setReply] = useState({ message: '', close: false })
  const [f, setF] = useState({})

  const residents = useApi(
    () => residentApi.list({ status: 'live', branch_id: activeBranchId, page_size: 200 }),
    [activeBranchId], { enabled: can('customers.view') })
  const queries = useApi(
    () => queryApi.list({ search, status, branch_id: activeBranchId, page_size: 50 }),
    [search, status, activeBranchId])

  const rows = queries.data?.items || []

  const openDetail = async (q) => {
    try {
      setDetail(await queryApi.get(q.id))
      setReply({ message: '', close: false })
    } catch (err) { error('Could not open it', err.message) }
  }

  const send = async () => {
    if (!reply.message.trim()) return error('Write a reply first.')
    setBusy(true)
    try {
      const updated = await queryApi.reply(detail.id, reply.message.trim(), reply.close)
      setDetail(updated)
      setReply({ message: '', close: false })
      success('Reply sent')
      queries.reload()
    } catch (err) { error('Could not send', err.message) }
    finally { setBusy(false) }
  }

  const create = async () => {
    if (!f.subject?.trim()) return error('Give the query a subject.')
    setBusy(true)
    try {
      await queryApi.create({
        resident_id: f.resident_id || null, category: f.category || 'General',
        subject: f.subject.trim(), message: f.message || null })
      success('Query logged')
      setOpen(false); setF({})
      queries.reload()
    } catch (err) { error('Could not log it', err.message) }
    finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Queries" subtitle="Questions from residents, and the answers given."
        actions={<PermissionGuard perm={['queries.create', 'queries.manage']}>
          <Button variant="primary" icon={Plus}
            onClick={() => { setF({ category: 'General' }); setOpen(true) }}>Log a query</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Open" value={num(rows.filter((q) => q.status === 'OPEN').length)}
          icon={MessageCircleQuestion} tone="amber" />
        <StatCard label="Answered"
          value={num(rows.filter((q) => q.status === 'ANSWERED').length)} tone="emerald" />
        <StatCard label="Closed"
          value={num(rows.filter((q) => q.status === 'CLOSED').length)} tone="slate" />
        <StatCard label="Total" value={num(rows.length)} tone="brand" />
      </div>

      <Card>
        <div className="p-4 border-b border-line">
          <FilterBar search={search} onSearch={setSearch}
            searchPlaceholder="Search subject…"
            filters={[{ key: 'status', label: 'Status', value: status,
              onChange: setStatus, options: ['OPEN', 'ANSWERED', 'CLOSED'] }]} />
        </div>

        {queries.error ? (
          <InlineAlert tone="error" className="m-4">{queries.error.message}</InlineAlert>
        ) : queries.loading && !queries.data ? (
          <div className="p-4 space-y-2">{[0, 1, 2].map((i) =>
            <Skeleton key={i} className="h-14" />)}</div>
        ) : (
          <DataTable rows={rows} pageSize={50} onRowClick={openDetail}
            columns={[
              { key: 'ticket_number', header: 'Query',
                render: (q) => <div><p className="font-medium text-slate-900">{q.ticket_number}</p>
                  <p className="text-xs text-slate-500 truncate">{q.subject}</p></div> },
              { key: 'category', header: 'Topic',
                render: (q) => <StatusBadge status={q.category} tone="slate" /> },
              { key: 'resident', header: 'From', sortable: false,
                render: (q) => <span className="text-sm text-slate-700">{q.resident || 'Staff'}</span> },
              { key: 'message_count', header: 'Messages', align: 'right',
                render: (q) => <span className="tnum text-slate-600">{q.message_count}</span> },
              { key: 'created_at', header: 'Age',
                render: (q) => <span className="text-xs text-slate-500">{relative(q.created_at)}</span> },
              { key: 'status', header: 'Status',
                render: (q) => <StatusBadge status={q.status} tone={TONE[q.status]} dot /> },
            ]}
            mobileCard={(q) => (
              <div className="space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">{q.subject}</p>
                    <p className="text-xs text-slate-500">{q.ticket_number} · {q.category}</p>
                  </div>
                  <StatusBadge status={q.status} tone={TONE[q.status]} />
                </div>
                <p className="text-2xs text-slate-400">
                  {q.resident || 'Staff'} · {relative(q.created_at)}</p>
              </div>
            )}
            empty={<EmptyState icon={MessageCircleQuestion} title="No queries"
              message="Residents ask questions from their own portal." />} />
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} size="sm" title="Log a query"
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={create}>Log it</Button></>}>
        <div className="space-y-4">
          <FormField label="Resident" hint="Leave blank for a general note.">
            <Select value={f.resident_id || ''}
              onChange={(e) => setF({ ...f, resident_id: e.target.value })}>
              <option value="">Not resident-specific</option>
              {(residents.data?.items || []).map((r) => (
                <option key={r.id} value={r.id}>{r.full_name}</option>
              ))}
            </Select>
          </FormField>
          <FormField label="Topic">
            <Select value={f.category || 'General'}
              onChange={(e) => setF({ ...f, category: e.target.value })}>
              {['General', 'Billing', 'Room', 'Food', 'Policy'].map((c) => <option key={c}>{c}</option>)}
            </Select>
          </FormField>
          <FormField label="Subject" required>
            <Input value={f.subject || ''} onChange={(e) => setF({ ...f, subject: e.target.value })} />
          </FormField>
          <FormField label="Details">
            <Textarea rows={3} value={f.message || ''}
              onChange={(e) => setF({ ...f, message: e.target.value })} />
          </FormField>
        </div>
      </Modal>

      <Modal open={!!detail} onClose={() => setDetail(null)} size="md"
        title={detail?.subject} subtitle={`${detail?.ticket_number} · ${detail?.category}`}
        footer={<><Button onClick={() => setDetail(null)}>Close</Button>
          <PermissionGuard perm={['queries.respond', 'queries.manage']}>
            <Button variant="primary" icon={Send} loading={busy} onClick={send}>Send reply</Button>
          </PermissionGuard></>}>
        {detail && (
          <div className="space-y-4">
            <StatusBadge status={detail.status} tone={TONE[detail.status]} dot />
            <div className="space-y-3 max-h-64 overflow-y-auto">
              {detail.messages?.map((m) => (
                <div key={m.id}
                  className={`rounded-lg p-3 ${m.is_staff ? 'bg-brand-50' : 'bg-slate-50'}`}>
                  <p className="text-sm text-slate-800">{m.message}</p>
                  <p className="text-2xs text-slate-500 mt-1">
                    {m.author}{m.is_staff ? ' · staff' : ''} · {relative(m.created_at)}
                  </p>
                </div>
              ))}
            </div>
            <PermissionGuard perm={['queries.respond', 'queries.manage']}>
              <div className="space-y-3 pt-2 border-t border-line">
                <FormField label="Reply">
                  <Textarea rows={3} value={reply.message}
                    onChange={(e) => setReply({ ...reply, message: e.target.value })} />
                </FormField>
                <Checkbox checked={reply.close}
                  onChange={(e) => setReply({ ...reply, close: e.target.checked })}
                  label="Close the query" description="Marks it answered and closed." />
              </div>
            </PermissionGuard>
          </div>
        )}
      </Modal>
    </>
  )
}
