import { useEffect, useState } from 'react'
import { ShieldAlert, CircleCheck, CircleAlert } from 'lucide-react'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Toggle, FormField, Input, Select, Button, InlineAlert, Skeleton,
} from '@/components/ui'
import { useToast } from '@/context/ToastContext'
import { useApi, useMutation } from '@/lib/useApi'
import { platformSettingsApi } from '@/services/api/platformSettingsApi'
import { SmtpCard } from './SmtpCard'

/**
 * Every field this screen may write, and how to coerce it.
 *
 * A list rather than a hand-written object literal, because the literal was
 * wrong: `email_provider` was added to the form, the card and the API schema,
 * and forgotten here - so Save wrote every setting except the one the operator
 * had just changed, and the provider silently stayed on SMTP. Nothing failed;
 * the test simply reported on a transport they thought they had left.
 *
 * Mirrors WRITABLE in platform_settings_service.py. Secrets are absent from
 * both on purpose - they take their own encrypting endpoints.
 */
const WRITABLE = {
  default_trial_days: Number,
  grace_period_days: Number,
  expiry_warning_days: Number,
  native_session_days: Number,
  smtp_port: Number,

  auto_suspend_after_grace: Boolean,
  notify_email_enabled: Boolean,
  notify_sms_enabled: Boolean,
  notify_whatsapp_enabled: Boolean,
  smtp_use_tls: Boolean,
  smtp_use_ssl: Boolean,

  platform_name: String,
  email_provider: String,
  support_email: null,
  smtp_host: null,
  smtp_username: null,
  smtp_from_email: null,
  smtp_from_name: null,
  brevo_sender_email: null,
  brevo_sender_name: null,
}

/** `null` in WRITABLE means "a string the API accepts as empty". */
function buildPayload(form) {
  const out = {}
  for (const [key, cast] of Object.entries(WRITABLE)) {
    const value = form[key]
    if (cast === Number) out[key] = Number(value) || undefined
    else if (cast === Boolean) out[key] = !!value
    else out[key] = value || null
  }
  // Numeric fields the API bounds-checks must not arrive as undefined.
  out.default_trial_days = Number(form.default_trial_days) || 30
  out.grace_period_days = Number(form.grace_period_days) || 0
  out.expiry_warning_days = Number(form.expiry_warning_days) || 0
  out.native_session_days = Number(form.native_session_days) || 3650
  out.smtp_port = Number(form.smtp_port) || 587
  return out
}

const TRIAL_OPTIONS = ['7', '14', '30', '60']
const GRACE_OPTIONS = ['0', '3', '7', '15', '30']
const WARNING_OPTIONS = ['0', '3', '7', '15', '30']

/** Which toggle maps to which entry in the server's `channels` report. */
const CHANNELS = [
  { key: 'notify_email_enabled', channel: 'email', label: 'Email',
    description: 'Transactional notices and credentials' },
  { key: 'notify_whatsapp_enabled', channel: 'whatsapp', label: 'WhatsApp',
    description: 'Requires a Business API provider' },
  { key: 'notify_sms_enabled', channel: 'sms', label: 'SMS',
    description: 'Requires a DLT-registered sender' },
]

/**
 * Platform settings.
 *
 * Two things this screen must not do. It must not report a save that did not
 * reach the database — every value here is persisted through the API and the
 * form is re-seeded from the response. And it must not imply a notification
 * channel is delivering when no provider is configured: the toggle records
 * intent, the badge beside it reports what the deployment can actually send,
 * and they are shown as the two separate facts they are.
 */
export default function MasterSettings() {
  const { success, error } = useToast()
  const settings = useApi(() => platformSettingsApi.get(), [])

  const [form, setForm] = useState(null)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    if (settings.data) { setForm(settings.data); setDirty(false) }
  }, [settings.data])

  const set = (k) => (v) => {
    setForm((x) => ({ ...x, [k]: v?.target ? v.target.value : v }))
    setDirty(true)
  }

  const save = useMutation(
    () => platformSettingsApi.update(buildPayload(form)),
    {
      onSuccess: (data) => {
        // Re-seed from the response, not from local state: what the server
        // stored is the truth, including anything it normalised.
        setForm(data)
        setDirty(false)
        success('Platform settings saved')
      },
      onError: (err) => error('Could not save settings', err.message),
    })

  if (settings.loading && !form) {
    return (
      <>
        <PageHeader title="Platform settings" subtitle="Defaults applied to every tenant on PGuru." />
        <div className="grid lg:grid-cols-2 gap-4">
          {[0, 1].map((i) => <Card key={i} className="p-5 space-y-3">
            <Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" />
          </Card>)}
        </div>
      </>
    )
  }

  if (settings.error || !form) {
    return (
      <>
        <PageHeader title="Platform settings" />
        <Card className="p-5">
          <InlineAlert tone="error">
            Could not load platform settings. {settings.error?.message}{' '}
            <button onClick={settings.reload} className="underline">Retry</button>
          </InlineAlert>
        </Card>
      </>
    )
  }

  const channels = form.channels || {}

  return (
    <>
      <PageHeader title="Platform settings"
        subtitle="Defaults applied to every tenant on PGuru."
        actions={
          <Button variant="primary" disabled={!dirty || save.busy} loading={save.busy}
            onClick={() => save.run()}>
            {save.busy ? 'Saving…' : 'Save changes'}
          </Button>} />

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Subscription defaults" />
          <div className="p-5 space-y-4">
            <FormField label="Default trial length" hint="Applied when a PG is registered with a trial.">
              <Select value={String(form.default_trial_days)} onChange={set('default_trial_days')}>
                {TRIAL_OPTIONS.map((d) => <option key={d} value={d}>{d} days</option>)}
              </Select>
            </FormField>
            <FormField label="Grace period after expiry"
              hint="Read-only access before the account is suspended.">
              <Select value={String(form.grace_period_days)} onChange={set('grace_period_days')}>
                {GRACE_OPTIONS.map((d) => <option key={d} value={d}>{d} days</option>)}
              </Select>
            </FormField>
            <Toggle checked={form.auto_suspend_after_grace} onChange={set('auto_suspend_after_grace')}
              label="Suspend automatically after the grace period"
              description="Tenants keep read access but cannot create or edit records." />
          </div>
        </Card>

        <SmtpCard form={form} onChange={set} dirty={dirty}
          onSaved={(data) => setForm((f) => ({
            // Merge, never replace. Saving a secret returns the whole settings
            // object, and assigning it wholesale silently discarded any edit
            // the operator had made but not yet saved - most visibly the
            // provider dropdown, which then tested the wrong transport and
            // reported an error about a server they had just switched away
            // from. Only the fields the server alone knows are taken.
            ...f,
            smtp_password_set: data.smtp_password_set,
            smtp_password_readable: data.smtp_password_readable,
            smtp_verified_at: data.smtp_verified_at,
            brevo_api_key_set: data.brevo_api_key_set,
            brevo_api_key_readable: data.brevo_api_key_readable,
            brevo_verified_at: data.brevo_verified_at,
            channels: data.channels,
          }))} />

        <Card>
          <CardHeader title="Expiry warnings"
            subtitle="How long before expiry tenants are warned" />
          <div className="p-5 space-y-4">
            <FormField label="Warn before expiry"
              hint="A single lead time, enforced by the subscription sweep.">
              <Select value={String(form.expiry_warning_days)} onChange={set('expiry_warning_days')}>
                {WARNING_OPTIONS.map((d) => (
                  <option key={d} value={d}>{d === '0' ? 'No warning' : `${d} days before`}</option>
                ))}
              </Select>
            </FormField>
            <FormField label="Platform name" hint="Shown in notices sent to tenants.">
              <Input value={form.platform_name || ''} onChange={set('platform_name')} />
            </FormField>
            <FormField label="Support email" hint="Where tenants are told to write.">
              <Input type="email" value={form.support_email || ''} onChange={set('support_email')}
                placeholder="support@example.com" />
            </FormField>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="Notification channels"
            subtitle="How platform notices reach PG owners" />
          <div className="p-5 space-y-3">
            <InlineAlert tone="info" icon={ShieldAlert}>
              A switch here records that you want a channel used. Whether it can actually
              deliver depends on provider credentials in the deployment environment, shown
              against each channel below. Turning one on does not make an unconfigured
              provider start sending.
            </InlineAlert>
            <div className="divide-y divide-line">
              {CHANNELS.map(({ key, channel, label, description }) => {
                const status = channels[channel]
                const ready = status?.configured
                return (
                  <div key={key} className="py-1">
                    <Toggle checked={Boolean(form[key])} onChange={set(key)}
                      ariaLabel={label}
                      label={
                        <span className="flex items-center gap-2">
                          {label}
                          <span className={`inline-flex items-center gap-1 text-2xs font-medium rounded px-1.5 py-0.5 ${
                            ready ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                            {ready ? <CircleCheck size={11} /> : <CircleAlert size={11} />}
                            {ready ? 'Configured' : 'Not configured'}
                          </span>
                        </span>
                      }
                      description={status?.detail || description} />
                  </div>
                )
              })}
            </div>
          </div>
        </Card>
      </div>
    </>
  )
}
