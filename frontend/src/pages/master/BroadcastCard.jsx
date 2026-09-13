/**
 * A message from the platform operator to every app user.
 *
 * Distinct from an Announcement, which belongs to one PG and is written by its
 * owner. This one crosses tenants, so only a master admin can send it and it is
 * never attributed to a PG - "your PG says the app is down on Sunday" is a lie
 * that sends calls to the wrong people.
 *
 * The whole design of this screen is about the fact that it cannot be undone.
 * The reach is shown before the box is typed in, the confirmation is a
 * deliberate second action, and the button says the number out loud. A send
 * that turns out to have a typo in it has already reached every phone.
 */
import { useEffect, useState } from 'react'
import { Megaphone, Send, Users, Smartphone } from 'lucide-react'
import {
  Card, CardHeader, CardBody, Button, FormField, Input, Textarea,
  InlineAlert, Select, Checkbox,
} from '@/components/ui'
import { useToast } from '@/context/ToastContext'
import { platformSettingsApi } from '@/services/api/platformSettingsApi'

export function BroadcastCard() {
  const toast = useToast()
  const [reach, setReach] = useState(null)
  const [title, setTitle] = useState('')
  const [message, setMessage] = useState('')
  const [audience, setAudience] = useState('all')
  const [confirm, setConfirm] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [sent, setSent] = useState(null)

  useEffect(() => {
    platformSettingsApi.broadcastReach().then(setReach).catch(() => setReach(null))
  }, [])

  // The count for the audience actually selected, not the grand total. An
  // operator sending to residents only should not be shown the staff number
  // and then be surprised by who replied.
  const target = !reach ? null
    : audience === 'staff' ? reach.staff
    : audience === 'residents' ? reach.residents
    : reach.total

  const ready = title.trim().length >= 3 && message.trim().length >= 3 && confirm

  const send = async () => {
    setSending(true); setError(null)
    try {
      const result = await platformSettingsApi.broadcast({
        title: title.trim(), message: message.trim(), audience, confirm: true,
      })
      setSent(result)
      setTitle(''); setMessage(''); setConfirm(false)
      toast.success(`Queued for ${result.recipients} people.`)
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

        {sent && (
          <InlineAlert tone="success">
            Queued for {sent.recipients} {sent.recipients === 1 ? 'person' : 'people'}
            {' '}({sent.staff} staff, {sent.residents} residents). Delivery starts
            within a few seconds.
          </InlineAlert>
        )}

        <InlineAlert tone="warn" icon={Megaphone}>
          This reaches every user of every PG on the platform and cannot be
          recalled once sent. It arrives as a notification, not an email.
        </InlineAlert>

        {reach && (
          <div className="flex flex-wrap gap-4 text-sm text-slate-600">
            <span className="inline-flex items-center gap-1.5">
              <Users size={15} className="text-slate-400" />
              {reach.staff} staff · {reach.residents} residents
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Smartphone size={15} className="text-slate-400" />
              {reach.devices} {reach.devices === 1 ? 'phone' : 'phones'} registered
            </span>
          </div>
        )}

        {reach && reach.devices === 0 && (
          <InlineAlert tone="info">
            No phone has the app installed and signed in yet, so nothing would
            buzz. The message would still appear in everyone's notification list
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
            : `I understand this goes to ${target} ${target === 1 ? 'person' : 'people'} and cannot be recalled`}
        />

        <Button variant="primary" icon={Send} loading={sending}
          disabled={!ready || sending} onClick={send}>
          {target === null ? 'Send broadcast' : `Send to ${target}`}
        </Button>

        <p className="text-xs text-slate-500">
          Anyone who has turned notifications off in their own profile is
          skipped on the phone but still sees it in the app.
        </p>
      </CardBody>
    </Card>
  )
}