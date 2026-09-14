import { useState } from 'react'
import { LifeBuoy, Plus, Send, CheckCircle2 } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { platformSupportApi } from '@/services/api/platformSupportApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, CardBody, Button, EmptyState, Modal, FormField, Input,
  Select, Textarea, InlineAlert, Skeleton, StatusBadge,
} from '@/components/ui'
import { dateFmt } from '@/lib/format'

const CATEGORIES = [
  ['payment', 'Payment or billing'],
  ['bug', 'Something is broken'],
  ['feature', 'Feature request'],
  ['question', 'Question'],
  ['other', 'Other'],
]
const PRIORITIES = [['low', 'Low'], ['normal', 'Normal'],
                    ['high', 'High'], ['urgent', 'Urgent']]

/**
 * Where a PG owner asks the platform for help.
 *
 * Not the Query centre, which is residents asking this PG. Those two look alike
 * and run in opposite directions, and an owner who cannot tell them apart ends
 * up posting a billing problem where their own residents can read it.
 */
export default function DeveloperSupport() {
  const { success, error } = useToast()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(null)
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({ subject: '', body: '', category: 'question',
                               priority: 'normal' })

  const tickets = useApi(() => platformSupportApi.list(), [])

  async function create() {
    setBusy(true)
    try {
      await platformSupportApi.create(f)
      success('Ticket raised. Replies appear here.')
      setOpen(false)
      setF({ subject: '', body: '', category: 'question', priority: 'normal' })
      tickets.refetch?.()
    } catch (e) { error(e.message || 'Could not raise that ticket') }
    finally { setBusy(false) }
  }

  async function sendReply() {
    if (!reply.trim()) return
    setBusy(true)
    try {
      const updated = await platformSupportApi.reply(active.id, reply.trim())
      setActive(updated)
      setReply('')
      tickets.refetch?.()
    } catch (e) { error(e.message || 'Could not send that reply') }
    finally { setBusy(false) }
  }

  async function closeTicket(id) {
    try {
      await platformSupportApi.close(id)
      success('Ticket closed')
      setActive(null)
      tickets.refetch?.()
    } catch (e) { error(e.message) }
  }

  const rows = tickets.data || []

  return (
    <PermissionGuard permission="settings.manage">
      <PageHeader
        title="Developer support"
        subtitle="Ask the PGuru team about a payment, a bug or anything else."
        actions={<Button variant="primary" icon={Plus}
          onClick={() => setOpen(true)}>Raise a ticket</Button>}
      />

      <InlineAlert tone="info" className="mb-4">
        This reaches the PGuru team, not your residents. For something a resident
        asked you, use the Query centre instead.
      </InlineAlert>

      {tickets.loading ? <Skeleton className="h-48" /> : rows.length === 0 ? (
        <Card><CardBody>
          <EmptyState icon={LifeBuoy} title="No tickets yet"
            message="Raise one if a payment looks wrong or something is not working."
            action={<Button variant="primary" icon={Plus}
              onClick={() => setOpen(true)}>Raise a ticket</Button>} />
        </CardBody></Card>
      ) : (
        <div className="space-y-3">
          {rows.map((t) => (
            <Card key={t.id}>
              <CardHeader
                title={t.subject}
                subtitle={`${t.reference} · ${dateFmt(t.created_at)} · ${t.category}`}
                action={
                  <div className="flex items-center gap-2">
                    {t.last_reply_by === 'platform'
                      && !['resolved', 'closed'].includes(t.status) && (
                      <span className="text-xs text-emerald-600 font-medium">
                        new reply
                      </span>
                    )}
                    <StatusBadge status={t.status} />
                  </div>
                }
              />
              <CardBody>
                <p className="text-sm text-slate-600 line-clamp-2">
                  {t.messages?.[t.messages.length - 1]?.body}
                </p>
                <Button variant="secondary" size="sm" className="mt-3"
                  onClick={() => { setActive(t); setReply('') }}>
                  Open conversation
                </Button>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {/* ------------------------------------------------------- new ---- */}
      <Modal open={open} onClose={() => setOpen(false)} title="Raise a ticket"
        subtitle="The PGuru team will reply here">
        <FormField label="Subject" required>
          <Input value={f.subject} placeholder="Payment shows as failed but money left my account"
            onChange={(e) => setF({ ...f, subject: e.target.value })} />
        </FormField>
        <div className="grid sm:grid-cols-2 gap-3">
          <FormField label="Category">
            <Select value={f.category}
              onChange={(e) => setF({ ...f, category: e.target.value })}>
              {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </FormField>
          <FormField label="Priority"
            hint="Urgent is for things stopping you working today.">
            <Select value={f.priority}
              onChange={(e) => setF({ ...f, priority: e.target.value })}>
              {PRIORITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </FormField>
        </div>
        <FormField label="What happened?" required
          hint="Dates, amounts and reference numbers get this answered fastest.">
          <Textarea rows={6} value={f.body}
            onChange={(e) => setF({ ...f, body: e.target.value })} />
        </FormField>
        <div className="mt-4 flex gap-2 justify-end">
          <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="primary" onClick={create}
            disabled={busy || f.subject.trim().length < 3 || f.body.trim().length < 5}>
            Send
          </Button>
        </div>
      </Modal>

      {/* ---------------------------------------------------- thread ---- */}
      <Modal open={!!active} onClose={() => setActive(null)}
        title={active?.subject} subtitle={active?.reference} size="lg">
        <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
          {active?.messages?.map((m) => (
            <div key={m.id}
              className={m.side === 'owner' ? 'text-right' : 'text-left'}>
              <div className={[
                'inline-block max-w-[85%] rounded-lg px-3 py-2 text-sm text-left',
                m.side === 'owner' ? 'bg-brand-50 text-slate-800'
                  : 'bg-slate-100 text-slate-800',
              ].join(' ')}>
                <div className="text-[11px] text-slate-500 mb-0.5">
                  {m.side === 'owner' ? 'You' : 'PGuru support'} ·{' '}
                  {dateFmt(m.created_at)}
                </div>
                <div className="whitespace-pre-wrap">{m.body}</div>
              </div>
            </div>
          ))}
        </div>

        {active && !['closed'].includes(active.status) && (
          <div className="mt-4 pt-4 border-t border-line">
            <FormField label="Reply">
              <Textarea rows={3} value={reply}
                onChange={(e) => setReply(e.target.value)} />
            </FormField>
            <div className="mt-3 flex gap-2 justify-between">
              <Button variant="ghost" icon={CheckCircle2}
                onClick={() => closeTicket(active.id)}>
                Close ticket
              </Button>
              <Button variant="primary" icon={Send} onClick={sendReply}
                disabled={busy || !reply.trim()}>Send reply</Button>
            </div>
          </div>
        )}
      </Modal>
    </PermissionGuard>
  )
}
