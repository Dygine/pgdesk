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

const TONE = { OPEN: 'amber', ANSWERED: 'blue', CLOSED: 'slate' }
/** Whose move it is. OPEN = the office owes a reply; ANSWERED = the resident does. */
const SAYS = { OPEN: 'Needs a reply', ANSWERED: 'Waiting on resident', CLOSED: 'Closed' }

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
      success(f.resident_id ? 'Query sent' : 'Note saved',
        f.resident_id ? 'The resident has been notified and can reply from their app.' : undefined)
      setOpen(false); setF({})
      queries.reload()
    } catch (err) { error('Could not log it', err.message) }
    finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Queries"
        subtitle="Questions residents ask, and questions you send them. Everything here shows up in the resident's app."
        actions={<PermissionGuard perm={['queries.create', 'queries.manage']}>
          <Button variant="primary" icon={Plus}
            onClick={() => { setF({ category: 'General' }); setOpen(true) }}>New query</Button>
        </PermissionGuard>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Needs a reply" value={num(rows.filter((q) => q.status === 'OPEN').length)}
          icon={MessageCircleQuestion} tone="amber" />
        <StatCard label="Waiting on resident"
          value={num(rows.filter((q) => q.status === 'ANSWERED').length)} tone="blue" />
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
              { key: 'resident', header: 'With', sortable: false,
                render: (q) => <div>
                  <p className="text-sm text-slate-700">{q.resident || 'Internal note'}</p>
                  <p className="text-2xs text-slate-500">{q.opened_by === 'staff'
                    ? (q.resident ? 'Sent by the office' : 'Office only') : 'Asked by resident'}</p></div> },
              { key: 'message_count', header: 'Messages', align: 'right',
                render: (q) => <span className="tnum text-slate-600">{q.message_count}</span> },
              { key: 'created_at', header: 'Age',
                render: (q) => <span className="text-xs text-slate-500">{relative(q.created_at)}</span> },
              { key: 'status', header: 'Status',
                render: (q) => <StatusBadge status={SAYS[q.status] || q.status} tone={TONE[q.status]} dot /> },
            ]}
            mobileCard={(q) => (
              <div className="space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">{q.subject}</p>
                    <p className="text-xs text-slate-500">{q.ticket_number} · {q.category}</p>
                  </div>
                  <StatusBadge status={SAYS[q.status] || q.status} tone={TONE[q.status]} />
                </div>
                <p className="text-2xs text-slate-400">
                  {q.resident ? `${q.opened_by === 'staff' ? 'To' : 'From'} ${q.resident}` : 'Internal note'} · {relative(q.created_at)}</p>
              </div>
            )}
            empty={<EmptyState icon={MessageCircleQuestion} title="No queries"
              message="Residents ask from their app. To ask a resident something, use New query." />} />
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} size="sm" title="New query"
        subtitle="Ask a resident something - it appears in their app under Ask the PG, with a notification."
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" icon={Send} loading={busy} onClick={create}>
            {f.resident_id ? 'Send to resident' : 'Save note'}</Button></>}>
        <div className="space-y-4">
          <FormField label="Send to" hint={f.resident_id
            ? 'They get a notification and can reply from their app.'
            : 'Without a resident this is an internal note nobody else sees.'}>
            <Select value={f.resident_id || ''}
              onChange={(e) => setF({ ...f, resident_id: e.target.value })}>
              <option value="">Nobody - internal note</option>
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
          <FormField label="Message">
            <Textarea rows={3} value={f.message || ''}
              onChange={(e) => setF({ ...f, message: e.target.value })}
              placeholder="Please drop a copy of your Aadhaar at the desk this week." />
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
            <div className="flex items-center gap-2 flex-wrap">
              <StatusBadge status={SAYS[detail.status] || detail.status} tone={TONE[detail.status]} dot />
              <span className="text-xs text-slate-500">
                {detail.resident ? `${detail.opened_by === 'staff' ? 'Sent to' : 'Asked by'} ${detail.resident}` : 'Internal note'}</span>
            </div>
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
