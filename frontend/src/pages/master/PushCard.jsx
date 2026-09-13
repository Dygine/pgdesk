/**
 * Firebase push configuration.
 *
 * Same shape as SmtpCard and for the same reasons: the credential is write-only
 * (the API reports whether a key is stored, never what it is), and "saved" is
 * shown as a different fact from "has actually delivered a message". A wrong
 * project or a revoked key both save perfectly and send nothing, so a screen
 * that only confirmed the save would be lying by omission.
 *
 * `onChange` is the curried setter from MasterSettings: `onChange('field')`
 * returns the handler. Same convention SmtpCard uses - a card that invented its
 * own would work until someone moved a field between the two.
 */
import { useState } from 'react'
import { CircleCheck, CircleAlert, Send, KeyRound, ShieldAlert } from 'lucide-react'
import {
  Card, CardHeader, CardBody, Button, FormField, Input, Textarea,
  InlineAlert, Toggle,
} from '@/components/ui'
import { useToast } from '@/context/ToastContext'
import { platformSettingsApi } from '@/services/api/platformSettingsApi'

export function PushCard({ form, onChange, onSaved }) {
  const toast = useToast()
  const [credentials, setCredentials] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState(null)

  const configured = Boolean(form.fcm_credentials_set)
  // A key stored before the application secret was rotated is still in the
  // column and can no longer be decrypted. Reported as its own state, because
  // the fix is "paste it again" and any other message would send an operator
  // hunting the wrong fault.
  const unreadable = configured && form.fcm_credentials_readable === false

  const saveKey = async () => {
    setSaving(true); setError(null)
    try {
      const data = await platformSettingsApi.setFcmCredentials(
        credentials || null, form.fcm_project_id || null)
      setCredentials('')
      toast.success(credentials
        ? 'Firebase key saved. Send a test notification to confirm it works.'
        : 'Firebase key cleared. Push notifications are off.')
      onSaved?.(data)
    } catch (err) {
      setError(err?.message || 'Could not save the key.')
    } finally {
      setSaving(false)
    }
  }

  const sendTest = async () => {
    setTesting(true); setError(null)
    try {
      const data = await platformSettingsApi.sendTestPush()
      toast.success('Test notification sent. Check your phone.')
      onSaved?.(data)
    } catch (err) {
      setError(err?.message || 'Firebase rejected the request.')
    } finally {
      setTesting(false)
    }
  }

  return (
    <Card>
      <CardHeader
        title="Push notifications"
        subtitle="Delivered to the installed app, including while it is closed"
        action={
          configured && !unreadable
            ? <span className="inline-flex items-center gap-1.5 text-xs text-emerald-700 shrink-0">
                <CircleCheck size={15} /> Key stored
              </span>
            : <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 shrink-0">
                <CircleAlert size={15} /> Not configured
              </span>
        }
      />
      <CardBody className="space-y-4">
        {error && <InlineAlert tone="error">{error}</InlineAlert>}

        {unreadable && (
          <InlineAlert tone="warn" icon={ShieldAlert}>
            A key is stored but can no longer be decrypted - the application
            secret changed since it was saved. Paste the service account key
            again below.
          </InlineAlert>
        )}

        {form.fcm_verified_at ? (
          <InlineAlert tone="success">
            Firebase accepted a test notification on{' '}
            {new Date(form.fcm_verified_at).toLocaleString()}.
          </InlineAlert>
        ) : configured && !unreadable ? (
          <InlineAlert tone="info">
            Saved, but nothing has been delivered yet. Send a test notification
            to prove it works.
          </InlineAlert>
        ) : null}

        <div className="divide-y divide-line">
          <div className="py-1">
            <Toggle
              checked={Boolean(form.notify_push_enabled)}
              onChange={onChange('notify_push_enabled')}
              label="Send push notifications"
              description="When off, notifications are still recorded in the app - they are just not pushed to phones." />
          </div>
          <div className="py-1">
            <Toggle
              checked={Boolean(form.push_to_residents)}
              onChange={onChange('push_to_residents')}
              label="To residents"
              description="Invoices, payments, announcements, gate passes, replies" />
          </div>
          <div className="py-1">
            <Toggle
              checked={Boolean(form.push_to_staff)}
              onChange={onChange('push_to_staff')}
              label="To owners and staff"
              description="Complaints, visitor requests, checkout notices" />
          </div>
        </div>

        <FormField label="Rent reminder"
          hint="Days before the due date to remind a resident. 0 turns reminders off. The invoice itself is always notified when it is raised.">
          <Input type="number" min="0" max="30" className="tnum"
            value={form.rent_reminder_days ?? 3}
            onChange={onChange('rent_reminder_days')} />
        </FormField>

        <FormField label="Firebase project ID"
          hint="Optional. Read from the key itself when left blank.">
          <Input value={form.fcm_project_id || ''} placeholder="pguru-5acbf"
            onChange={onChange('fcm_project_id')} />
        </FormField>

        <FormField
          label={configured ? 'Replace the service account key' : 'Service account key'}
          hint="Firebase -> Project settings -> Service accounts -> Generate new private key. Paste the whole file. This is NOT google-services.json, which belongs in the Android build.">
          <Textarea rows={5} spellCheck={false} value={credentials}
            className="font-mono text-xs"
            placeholder={configured
              ? 'Leave blank to keep the stored key'
              : '{"type": "service_account", "project_id": "..."}'}
            onChange={(e) => setCredentials(e.target.value)} />
        </FormField>

        <p className="text-xs text-slate-500">
          Stored encrypted. Nothing in the API reads it back - this screen can
          report that a key is stored, never what it is.
        </p>

        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon={KeyRound} loading={saving}
            disabled={saving || (!credentials && !configured)} onClick={saveKey}>
            {credentials ? 'Save key' : 'Clear key'}
          </Button>
          <Button icon={Send} loading={testing}
            disabled={testing || !configured || unreadable} onClick={sendTest}>
            Send test notification
          </Button>
        </div>

        {configured && (
          <p className="text-xs text-slate-500">
            The test goes to phones registered against your own account. Open
            PGuru on your phone, sign in and allow notifications first -
            otherwise there is nothing to deliver to.
          </p>
        )}
      </CardBody>
    </Card>
  )
}