import { useState } from 'react'
import { Plus, MessageCircleQuestion, UserPlus, DoorOpen, Send } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { meApi } from '@/services/api/meApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, StatusBadge, EmptyState, Skeleton, InlineAlert,
  Modal, FormField, Input, Select, Textarea, Tabs, StatCard,
} from '@/components/ui'
import { num, relative, dateTimeFmt } from '@/lib/format'

const TONE = { PENDING: 'amber', APPROVED: 'emerald', REJECTED: 'rose',
  INSIDE: 'brand', COMPLETED: 'slate', ACTIVE: 'brand', CANCELLED: 'slate',
  OPEN: 'amber', ANSWERED: 'emerald', CLOSED: 'slate' }

/** Queries, visitor requests and gate passes — everything the resident asks for. */
export default function MyRequests() {
  const { success, error } = useToast()
  const [tab, setTab] = useState('queries')
  const [modal, setModal] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})
  const [reply, setReply] = useState({})

  const queries = useApi(() => meApi.queries(), [])
  const visitors = useApi(() => meApi.visitors(), [])
  const passes = useApi(() => meApi.gatePasses(), [])

  const submit = async () => {
    setBusy(true)
    try {
      if (modal === 'query') {
        if (!f.subject?.trim()) throw new Error('Give your question a subject.')
        await meApi.ask({ category: f.category || 'General', subject: f.subject.trim(),
          message: f.message || null })
        success('Question sent')
        queries.reload()
      } else if (modal === 'visitor') {
        if (!f.name?.trim()) throw new Error('Who is visiting?')
        await meApi.requestVisitor({
          resident_id: '00000000-0000-0000-0000-000000000000',  // ignored by the API
          name: f.name.trim(), phone: f.phone || null, relation: f.relation || null,
          purpose: f.purpose || null, expected_at: f.expected_at || null })
        success('Visitor request sent', 'The front desk will approve it.')
        visitors.reload()
      } else {
        if (!f.reason?.trim()) throw new Error('Give a reason for the pass.')
        if (!f.from_at || !f.to_at) throw new Error('Set both a departure and a return time.')
        await meApi.requestGatePass({
          resident_id: '00000000-0000-0000-0000-000000000000',  // ignored by the API
          reason: f.reason.trim(), destination: f.destination || null,
          from_at: new Date(f.from_at).toISOString(),
          to_at: new Date(f.to_at).toISOString(),
          is_emergency: !!f.is_emergency })
        success('Gate pass requested')
        passes.reload()
      }
      setModal(null); setF({})
    } catch (err) { error('That did not go through', err.message) }
    finally { setBusy(false) }
  }

  const sendReply = async (q) => {
    const message = (reply[q.id] || '').trim()
    if (!message) return
    try {
      await meApi.replyToQuery(q.id, message)
      setReply((r) => ({ ...r, [q.id]: '' }))
      success('Reply sent')
      queries.reload()
    } catch (err) { error('Could not send that', err.message) }
  }

  const qRows = queries.data || []
  const vRows = visitors.data || []
  const pRows = passes.data || []

  return (
    <>
      <PageHeader title="My requests"
        subtitle="Questions, visitors and gate passes — and where each one stands."
        actions={<Button variant="primary" icon={Plus}
          onClick={() => { setF({}); setModal(tab === 'queries' ? 'query'
            : tab === 'visitors' ? 'visitor' : 'pass') }}>
          {tab === 'queries' ? 'Ask a question'
            : tab === 'visitors' ? 'Request a visitor' : 'Request a pass'}
        </Button>} />

      <div className="grid grid-cols-3 gap-3 sm:gap-4 mb-4">
        <StatCard label="Open questions"
          value={num(qRows.filter((q) => q.status === 'OPEN').length)}
          icon={MessageCircleQuestion} tone="amber" />
        <StatCard label="Visitors pending"
          value={num(vRows.filter((v) => v.status === 'PENDING').length)}
          icon={UserPlus} tone="brand" />
        <StatCard label="Passes approved"
          value={num(pRows.filter((p) => p.status === 'APPROVED').length)}
          icon={DoorOpen} tone="emerald" />
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'queries', label: 'Questions', count: qRows.length },
        { value: 'visitors', label: 'Visitors', count: vRows.length },
        { value: 'passes', label: 'Gate passes', count: pRows.length },
      ]} />

      <div className="mt-4 space-y-3">
        {tab === 'queries' && (
          queries.loading && !queries.data ? <Skeleton className="h-48" />
            : qRows.length === 0 ? (
              <Card><EmptyState icon={MessageCircleQuestion} title="No questions yet"
                message="Ask the office anything — billing, rooms, policies." /></Card>
            ) : qRows.map((q) => (
              <Card key={q.id}>
                <div className="p-4 sm:p-5">
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-slate-900">{q.subject}</p>
                      <p className="text-2xs text-slate-500">
                        {q.ticket_number} · {q.category} · {relative(q.created_at)}</p>
                    </div>
                    <StatusBadge status={q.status} tone={TONE[q.status]} dot />
                  </div>
                  <div className="space-y-2 border-l-2 border-line pl-3 my-3">
                    {q.messages.map((m, i) => (
                      <div key={i}>
                        <p className="text-sm text-slate-700">{m.message}</p>
                        <p className="text-2xs text-slate-400">
                          {m.author}{m.is_staff ? ' · staff' : ''} · {relative(m.created_at)}
                        </p>
                      </div>
                    ))}
                  </div>
                  {q.status !== 'CLOSED' && (
                    <div className="flex gap-2">
                      <Input value={reply[q.id] || ''} placeholder="Write a reply…"
                        onChange={(e) => setReply((r) => ({ ...r, [q.id]: e.target.value }))} />
                      <Button icon={Send} onClick={() => sendReply(q)}>Send</Button>
                    </div>
                  )}
                </div>
              </Card>
            ))
        )}

        {tab === 'visitors' && (
          vRows.length === 0 ? (
            <Card><EmptyState icon={UserPlus} title="No visitor requests"
              message="Let the front desk know before someone comes to see you." /></Card>
          ) : vRows.map((v) => (
            <Card key={v.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900">{v.name}</p>
                  <p className="text-xs text-slate-500">
                    {v.relation || 'Visitor'}{v.phone ? ` · ${v.phone}` : ''}
                    {v.purpose ? ` · ${v.purpose}` : ''}
                  </p>
                  <p className="text-2xs text-slate-400 tnum mt-1">
                    {v.entry_at ? `Arrived ${dateTimeFmt(v.entry_at)}`
                      : v.expected_at ? `Expected ${dateTimeFmt(v.expected_at)}`
                        : relative(v.created_at)}
                    {v.exit_at ? ` · left ${dateTimeFmt(v.exit_at)}` : ''}
                  </p>
                </div>
                <StatusBadge status={v.status} tone={TONE[v.status]} dot />
              </div>
            </Card>
          ))
        )}

        {tab === 'passes' && (
          pRows.length === 0 ? (
            <Card><EmptyState icon={DoorOpen} title="No gate passes"
              message="Request one before going away overnight." /></Card>
          ) : pRows.map((p) => (
            <Card key={p.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900">{p.reason}</p>
                  <p className="text-xs text-slate-500">
                    {p.pass_number}{p.destination ? ` · ${p.destination}` : ''}
                  </p>
                  <p className="text-2xs text-slate-400 tnum mt-1">
                    {dateTimeFmt(p.from_at)} → {dateTimeFmt(p.to_at)}
                  </p>
                  {p.decision_note && (
                    <p className="text-2xs text-slate-500 mt-1">Note: {p.decision_note}</p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  {p.is_emergency && <StatusBadge status="Emergency" tone="rose" />}
                  <StatusBadge status={p.status} tone={TONE[p.status]} dot />
                </div>
              </div>
            </Card>
          ))
        )}
      </div>

      <Modal open={!!modal} onClose={() => setModal(null)} size="sm"
        title={modal === 'query' ? 'Ask a question'
          : modal === 'visitor' ? 'Request a visitor' : 'Request a gate pass'}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>Send request</Button></>}>
        {modal === 'query' && (
          <div className="space-y-4">
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
        )}
        {modal === 'visitor' && (
          <div className="space-y-4">
            <FormField label="Visitor name" required>
              <Input value={f.name || ''} onChange={(e) => setF({ ...f, name: e.target.value })} />
            </FormField>
            <div className="grid grid-cols-2 gap-3">
              <FormField label="Phone">
                <Input value={f.phone || ''} onChange={(e) => setF({ ...f, phone: e.target.value })} />
              </FormField>
              <FormField label="Relation">
                <Input value={f.relation || ''} placeholder="Father"
                  onChange={(e) => setF({ ...f, relation: e.target.value })} />
              </FormField>
            </div>
            <FormField label="Expected arrival">
              <Input type="datetime-local" value={f.expected_at || ''}
                onChange={(e) => setF({ ...f, expected_at: e.target.value })} />
            </FormField>
            <FormField label="Purpose">
              <Input value={f.purpose || ''} onChange={(e) => setF({ ...f, purpose: e.target.value })} />
            </FormField>
          </div>
        )}
        {modal === 'pass' && (
          <div className="space-y-4">
            <FormField label="Reason" required>
              <Input value={f.reason || ''} placeholder="Home visit"
                onChange={(e) => setF({ ...f, reason: e.target.value })} />
            </FormField>
            <FormField label="Destination">
              <Input value={f.destination || ''}
                onChange={(e) => setF({ ...f, destination: e.target.value })} />
            </FormField>
            <div className="grid grid-cols-2 gap-3">
              <FormField label="Leaving" required>
                <Input type="datetime-local" value={f.from_at || ''}
                  onChange={(e) => setF({ ...f, from_at: e.target.value })} />
              </FormField>
              <FormField label="Returning" required>
                <Input type="datetime-local" value={f.to_at || ''}
                  onChange={(e) => setF({ ...f, to_at: e.target.value })} />
              </FormField>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

/**
 * The router keeps separate nav entries for visitors, gate passes and queries.
 * They are three views of the same request centre, so each renders it with the
 * matching tab already open rather than duplicating the page three times.
 */
export const MyVisitors = MyRequests
export const MyGatePass = MyRequests
export const MyQueries = MyRequests
