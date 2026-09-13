/**
 * A message from the platform operator to every app user, with live delivery.
 *
 * Distinct from an Announcement, which belongs to one PG and is written by its
 * owner. This crosses tenants, so only a master admin can send it and it is
 * never attributed to a PG - "your PG says the app is down on Sunday" is a lie
 * that sends calls to the wrong people.
 *
 * Two things this screen is careful about.
 *
 * It cannot be undone, so the reach is shown before the box is typed in and the
 * confirmation names the number.
 *
 * And it does not pretend delivery is instant. The sweep runs every ten
 * seconds; a few thousand rows take several passes. So after sending, the
 * counts are polled and shown climbing. "Queued for 61" with no follow-up left
 * the operator with no way to tell a working system from a broken one.
 */
import { useEffect, useRef, useState } from 'react'
import {
  Megaphone, Send, Users, Smartphone, BellRing, Check, CircleAlert, Clock, Eye,
} from 'lucide-react'
import {
  Card, CardHeader, CardBody, Button, FormField, Input, Textarea,
  InlineAlert, Select, Checkbox,
} from '@/components/ui'
import { useToast } from '@/context/ToastContext'
import { platformSettingsApi } from '@/services/api/platformSettingsApi'

/** One number with its label. Four of these beat one sentence with four numbers. */
function Stat({ icon: Icon, value, label, tone = 'slate' }) {
  const tones = {
    slate: 'text-slate-600 bg-slate-50',
    green: 'text-emerald-700 bg-emerald-50',
    amber: 'text-amber-700 bg-amber-50',
    brand: 'text-brand-600 bg-brand-50',
  }
  return (
    <div className="flex-1 min-w-[88px] rounded-lg border border-line p-2.5">
      <div className={`inline-flex items-center justify-center h-7 w-7 rounded-md mb-1.5 ${tones[tone]}`}>
        <Icon size={15} aria-hidden="true" />
      </div>
      <p className="text-lg font-semibold text-slate-900 tnum leading-none">{value}</p>
      <p className="text-xs text-slate-500 mt-1">{label}</p>
    </div>
  )
}

export function BroadcastCard() {
  const toast = useToast()
  const [reach, setReach] = useState(null)
  const [title, setTitle] = useState('')
  const [message, setMessage] = useState('')
  const [audience, setAudience] = useState('all')
  const [confirm, setConfirm] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [stats, setStats] = useState(null)
  const timer = useRef(null)

  useEffect(() => {
    platformSettingsApi.broadcastReach().then(setReach).catch(() => setReach(null))
    // Any poll still scheduled when this card unmounts would keep hitting the
    // API from a screen nobody is looking at.
    return () => clearInterval(timer.current)
  }, [])

  const poll = (id) => {
    clearInterval(timer.current)
    const tick = async () => {
      try {
        const s = await platformSettingsApi.broadcastStats(id)
        setStats(s)
        // Stopped on the queue being empty rather than after N seconds: a slow
        // batch would otherwise be reported as finished while rows are still
        // going out.
        if (s?.complete) clearInterval(timer.current)
      } catch {
        clearInterval(timer.current)
      }
    }
    tick()
    timer.current = setInterval(tick, 3000)
  }

  // The count for the audience actually chosen, not the grand total. An
  // operator sending to residents only should not be shown the staff number
  // and then be surprised by who replied.
  const target = !reach ? null
    : audience === 'staff' ? reach.staff
    : audience === 'residents' ? reach.residents
    : reach.total

  const ready = title.trim().length >= 3 && message.trim().length >= 3 && confirm

  const send = async () => {
    setSending(true); setError(null); setStats(null)
    try {
      const result = await platformSettingsApi.broadcast({
        title: title.trim(), message: message.trim(), audience, confirm: true,
      })
      setTitle(''); setMessage(''); setConfirm(false)
      toast.success(`Queued for ${result.recipients}. Watching delivery…`)
      poll(result.broadcast_id)
    } catch (err) {
      setError(err?.message || 'Could not send.')
    } finally {
      setSending(false)
    }
  }

  return (
    <Card>
      <CardHeader title="Broadcast to all users"
        subtitle="One message from the platform to every PG owner, staff member and resident" />
      <CardBody className="space-y-4">
        {error && <InlineAlert tone="error">{error}</InlineAlert>}

        {stats && (
          <div className="space-y-2.5">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium text-slate-900 truncate">{stats.title}</p>
              {stats.complete
                ? <span className="text-xs text-emerald-700 shrink-0">Finished</span>
                : <span className="text-xs text-slate-500 shrink-0 animate-pulse">Sending…</span>}
            </div>
            <div className="flex gap-2 flex-wrap">
              <Stat icon={Users} value={stats.sent} label="In the app" />
              <Stat icon={Check} value={stats.delivered} label="On phones" tone="green" />
              <Stat icon={Eye} value={stats.read} label="Read" tone="brand" />
              {stats.pending > 0 && (
                <Stat icon={Clock} value={stats.pending} label="Queued" tone="amber" />
              )}
              {stats.failed > 0 && (
                <Stat icon={CircleAlert} value={stats.failed} label="No phone" tone="amber" />
              )}
            </div>
            <p className="text-xs text-slate-500">
              "No phone" covers people who have not installed the app and those
              who turned notifications off. They still see it in the app.
              {!stats.complete && ' Counts refresh every few seconds.'}
            </p>
          </div>
        )}

        <InlineAlert tone="warn" icon={Megaphone}>
          This reaches every user of every PG on the platform and cannot be
          recalled once sent. It arrives as a notification, not an email.
        </InlineAlert>

        {reach && (
          <div className="flex gap-2 flex-wrap">
            <Stat icon={Users} value={reach.total} label="Total users" />
            <Stat icon={BellRing} value={reach.opted_in} label="Notifications on" />
            <Stat icon={Smartphone} value={reach.reachable} label="Will buzz" tone="green" />
          </div>
        )}

        {reach && reach.reachable === 0 && (
          <InlineAlert tone="info">
            Nobody has the app installed and signed in yet, so no phone will
            buzz. The message still appears in everyone's notification list
            inside the app.
          </InlineAlert>
        )}

        <FormField label="Who receives it">
          <Select value={audience} onChange={(e) => setAudience(e.target.value)}>
            <option value="all">Everyone</option>
            <option value="staff">Owners and staff only</option>
            <option value="residents">Residents only</option>
          </Select>
        </FormField>

        <FormField label="Title"
          hint="Shown in bold on the phone. Keep it short — Android truncates past about 40 characters.">
          <Input value={title} maxLength={200}
            placeholder="Planned maintenance on Sunday"
            onChange={(e) => setTitle(e.target.value)} />
        </FormField>

        <FormField label="Message">
          <Textarea rows={4} value={message} maxLength={2000}
            placeholder="PGuru will be unavailable between 2am and 4am on Sunday while we upgrade the servers. No action is needed."
            onChange={(e) => setMessage(e.target.value)} />
        </FormField>

        <Checkbox checked={confirm} onChange={(e) => setConfirm(e.target.checked)}
          label={target === null
            ? 'I understand this cannot be recalled'
            : `I understand this goes to ${target} ${target === 1 ? 'person' : 'people'} and cannot be recalled`} />

        <Button variant="primary" icon={Send} loading={sending}
          disabled={!ready || sending} onClick={send}>
          {target === null ? 'Send broadcast' : `Send to ${target}`}
        </Button>
      </CardBody>
    </Card>
  )
}
