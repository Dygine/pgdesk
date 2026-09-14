import { useState } from 'react'
import { LifeBuoy, Send, Lock, CheckCircle2, RefreshCw } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { masterTicketApi } from '@/services/api/platformSupportApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, CardBody, Button, DataTable, StatusBadge, EmptyState,
  StatCard, Modal, FormField, Select, Textarea, Skeleton, InlineAlert,
} from '@/components/ui'
import { dateFmt } from '@/lib/format'

const STATUSES = ['open', 'in_progress', 'waiting', 'resolved', 'closed']

/**
 * The support queue.
 *
 * Sorted oldest-waiting first, not newest first: a queue sorted by recency
 * quietly starves whoever has waited longest, which is the person most likely
 * to be angry about it.
 */
export default function Tickets() {
  const { success, error } = useToast()
  const [filter, setFilter] = useState('')
  const [active, setActive] = useState(null)
  const [reply, setReply] = useState('')
  const [internal, setInternal] = useState(false)
  const [nextStatus, setNextStatus] = useState('')
  const [busy, setBusy] = useState(false)

  const queue = useApi(() => masterTicketApi.queue(filter || undefined), [filter])
  const counts = queue.data?.counts
  const rows = queue.data?.data || []

  async function send() {
    if (!reply.trim()) return
    setBusy(true)
    try {
      const updated = await masterTicketApi.reply(active.id, {
        body: reply.trim(), internal, status: nextStatus || undefined,
      })
      setActive(updated)
      setReply(''); setInternal(false); setNextStatus('')
      queue.refetch?.()
      success(internal ? 'Note saved' : 'Reply sent')
    } catch (e) { error(e.message || 'Could not send that') }
    finally { setBusy(false) }
  }

  async function setStatus(id, status) {
    try {
      const updated = await masterTicketApi.setStatus(id, status)
      setActive(updated)
      queue.refetch?.()
    } catch (e) { error(e.message) }
  }

  return (
    <>
      <PageHeader
        title="Support tickets"
        subtitle="What PG owners have asked the platform"
        actions={<Button variant="ghost" icon={RefreshCw}
          onClick={() => queue.refetch?.()}>Refresh</Button>}
      />

      <div className="grid gap-4 sm:grid-cols-3 mb-4">
        <StatCard label="Awaiting your reply" value={counts?.awaiting_reply ?? 0}
          icon={LifeBuoy} tone="amber"
          sub="the number that actually needs you" />
        <StatCard label="Open" value={counts?.open ?? 0}
          sub="open, in progress or waiting" />
        <StatCard label="Resolved"
          value={counts?.by_status?.resolved ?? 0} sub="all time" />
      </div>

      <Card>
        <CardHeader title="Queue"
          subtitle="Oldest waiting first"
          action={
            <Select value={filter} onChange={(e) => setFilter(e.target.value)}
              className="w-40">
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s.replace('_', ' ')}</option>
              ))}
            </Select>
          } />
        {queue.loading ? <CardBody><Skeleton className="h-40" /></CardBody> : (
          <DataTable
            columns={[
              { key: 'reference', header: 'Ref',
                render: (t) => <span className="font-mono text-xs">{t.reference}</span> },
              { key: 'organization', header: 'PG' },
              { key: 'subject', header: 'Subject',
                render: (t) => (
                  <span>
                    {t.subject}
                    {t.last_reply_by === 'owner'
                      && !['resolved', 'closed'].includes(t.status) && (
                      <span className="ml-2 text-[11px] text-amber-600 font-medium">
                        waiting on you
                      </span>
                    )}
                  </span>
                ) },
              { key: 'category', header: 'Category' },
              { key: 'priority', header: 'Priority',
                render: (t) => <StatusBadge status={t.priority}
                  tone={t.priority === 'urgent' ? 'rose'
                    : t.priority === 'high' ? 'amber' : 'slate'} /> },
              { key: 'last_reply_at', header: 'Last activity',
                render: (t) => dateFmt(t.last_reply_at || t.created_at) },
              { key: 'status', header: 'Status',
                render: (t) => <StatusBadge status={t.status} /> },
            ]}
            rows={rows}
            onRowClick={(t) => { setActive(t); setReply('') }}
            empty={<EmptyState icon={LifeBuoy} title="Nothing in the queue"
              message="Tickets raised by PG owners land here." />}
          />
        )}
      </Card>

      <Modal open={!!active} onClose={() => setActive(null)}
        title={active?.subject}
        subtitle={active ? `${active.reference} · ${active.organization}` : ''}
        size="lg">
        {active && (
          <>
            <div className="flex gap-2 mb-3 flex-wrap">
              {STATUSES.map((s) => (
                <Button key={s} size="sm"
                  variant={active.status === s ? 'primary' : 'ghost'}
                  onClick={() => setStatus(active.id, s)}>
                  {s.replace('_', ' ')}
                </Button>
              ))}
            </div>

            <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
              {active.messages?.map((m) => (
                <div key={m.id}
                  className={m.side === 'platform' ? 'text-right' : 'text-left'}>
                  <div className={[
                    'inline-block max-w-[85%] rounded-lg px-3 py-2 text-sm text-left',
                    m.internal ? 'bg-amber-50 ring-1 ring-amber-200'
                      : m.side === 'platform' ? 'bg-brand-50' : 'bg-slate-100',
                  ].join(' ')}>
                    <div className="text-[11px] text-slate-500 mb-0.5 flex items-center gap-1">
                      {m.internal && <Lock size={11} />}
                      {m.internal ? 'Internal note' : m.author}
                      {' · '}{dateFmt(m.created_at)}
                    </div>
                    <div className="whitespace-pre-wrap">{m.body}</div>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 pt-4 border-t border-line">
              <FormField label={internal ? 'Internal note' : 'Reply to the owner'}>
                <Textarea rows={3} value={reply}
                  onChange={(e) => setReply(e.target.value)} />
              </FormField>

              {internal && (
                <InlineAlert tone="warning" className="mt-2">
                  A note to yourself. The PG owner never sees this, and it does
                  not change whose turn it is.
                </InlineAlert>
              )}

              <div className="mt-3 flex flex-wrap gap-2 items-center justify-between">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input type="checkbox" checked={internal}
                    onChange={(e) => setInternal(e.target.checked)} />
                  Internal note
                </label>
                <div className="flex gap-2 items-center">
                  <Select value={nextStatus} className="w-40"
                    onChange={(e) => setNextStatus(e.target.value)}>
                    <option value="">Leave status</option>
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>Set {s.replace('_', ' ')}</option>
                    ))}
                  </Select>
                  <Button variant="primary" icon={internal ? Lock : Send}
                    onClick={send} disabled={busy || !reply.trim()}>
                    {internal ? 'Save note' : 'Send reply'}
                  </Button>
                </div>
              </div>
            </div>
          </>
        )}
      </Modal>
    </>
  )
}
