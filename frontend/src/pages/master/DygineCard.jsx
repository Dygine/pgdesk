import { useState } from 'react'
import {
  Wallet, KeyRound, CircleCheck, CircleAlert, ShieldCheck, Copy,
} from 'lucide-react'
import {
  Card, CardHeader, FormField, Input, Button, Toggle, InlineAlert,
} from '@/components/ui'
import { useToast } from '@/context/ToastContext'
import { platformSettingsApi } from '@/services/api/platformSettingsApi'
import { platformRevenueApi } from '@/services/api/platformBillingApi'

/**
 * How PG owners pay this platform.
 *
 * Nothing here touches how residents pay their PG — that runs on each owner's
 * own Razorpay keys, configured per organisation, and is deliberately a
 * different screen in a different part of the app.
 *
 * Both secrets are write-only. The API never returns them, so the fields start
 * empty even when a value is stored and leaving one empty on save means "keep
 * what is there". A form that pre-filled a secret would be a way to read
 * secrets, which is the opposite of what encrypting them is for.
 *
 * "Saved" and "works" are shown as separate facts, for the same reason the mail
 * card does it: a wrong secret saves perfectly and fails on every call.
 */
export function DygineCard({ form, onChange, dirty, onSaved, className }) {
  const { success, error } = useToast()
  const [keySecret, setKeySecret] = useState('')
  const [webhookSecret, setWebhookSecret] = useState('')
  const [busy, setBusy] = useState(false)
  const [testing, setTesting] = useState(false)

  const configured = form.dygine_key_secret_set && form.dygine_key_id
  const verified = !!form.dygine_verified_at

  async function saveSecrets() {
    if (!keySecret && !webhookSecret) return
    setBusy(true)
    try {
      const data = await platformSettingsApi.setDygineSecrets({
        key_secret: keySecret || undefined,
        webhook_secret: webhookSecret || undefined,
      })
      setKeySecret(''); setWebhookSecret('')
      onSaved?.(data)
      success('Saved. Run the connection test to confirm it works.')
    } catch (e) {
      error(e.message || 'Could not save those secrets')
    } finally {
      setBusy(false)
    }
  }

  async function test() {
    setTesting(true)
    try {
      await platformRevenueApi.verifyDygine()
      success('Connected. Dygine Pay accepted these credentials.')
      onSaved?.({ dygine_verified_at: new Date().toISOString() })
    } catch (e) {
      error(e.message || 'Dygine Pay rejected the credentials or could not be reached')
    } finally {
      setTesting(false)
    }
  }

  const webhookUrl =
    `${window.location.origin.replace(/^https?:\/\/[^/]*$/, '')}` ||
    '<your API origin>'

  return (
    <Card className={className}>
      <CardHeader
        icon={Wallet}
        title="Dygine Pay"
        description="How PG owners pay you for their subscription. Separate from the Razorpay keys each PG uses to collect rent."
        right={
          configured ? (
            verified ? (
              <span className="inline-flex items-center gap-1 text-xs text-emerald-600">
                <CircleCheck size={14} /> verified
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-xs text-amber-600">
                <CircleAlert size={14} /> saved, not tested
              </span>
            )
          ) : null
        }
      />

      <div className="p-5 space-y-4">
        <Toggle
          checked={!!form.dygine_enabled}
          onChange={onChange('dygine_enabled')}
          label="Accept subscription payments"
          description="Off until you have entered a key pair and the test passes. While off, owners see a message rather than a broken payment button. This switch, the URL and the key id are saved by Save changes at the top of the page — the two secrets have their own button below."
        />

        {/* Paired: two short, related values that are read together. */}
        <div className="grid sm:grid-cols-2 gap-4">
          <FormField label="Dygine Pay URL"
            hint="Where your payments hub runs, e.g. https://dygine-pay.onrender.com">
            <Input value={form.dygine_base_url || ''}
              onChange={onChange('dygine_base_url')}
              placeholder="https://pay.dygine.com" />
          </FormField>

          <FormField label="Key id" hint="Starts with dgn_test_ or dgn_live_">
            <Input value={form.dygine_key_id || ''}
              onChange={onChange('dygine_key_id')}
              placeholder="dgn_test_xxxxxxxxxxxxxxxx" />
          </FormField>
        </div>

        <div className="pt-2 border-t">
          <p className="text-xs text-muted mb-3 flex items-start gap-1.5">
            <KeyRound size={13} className="mt-0.5 shrink-0" />
            <span>
              These two are different values and are easy to swap. The{' '}
              <strong>key secret</strong> authenticates you to Dygine on outbound
              calls. The <strong>webhook secret</strong> verifies events arriving
              back. Swap them and every call is rejected and every webhook fails
              its signature check.
            </span>
          </p>

          <div className="grid sm:grid-cols-2 gap-4">
          <FormField
            label="Key secret"
            hint={form.dygine_key_secret_set
              ? 'One is stored. Leave empty to keep it.'
              : 'Shown once when you issue the key in Dygine admin.'}
          >
            <Input type="password" value={keySecret}
              onChange={(e) => setKeySecret(e.target.value)}
              placeholder={form.dygine_key_secret_set ? '••••••••••••' : ''}
              autoComplete="new-password" />
          </FormField>

          <FormField
            label="Webhook secret"
            hint={form.dygine_webhook_secret_set
              ? 'One is stored. Leave empty to keep it.'
              : 'The same value you set on the webhook in Dygine admin.'}
          >
            <Input type="password" value={webhookSecret}
              onChange={(e) => setWebhookSecret(e.target.value)}
              placeholder={form.dygine_webhook_secret_set ? '••••••••••••' : ''}
              autoComplete="new-password" />
          </FormField>
          </div>

          <div className="flex gap-2 mt-3">
            <Button onClick={saveSecrets}
              disabled={busy || (!keySecret && !webhookSecret)}>
              Save secrets
            </Button>
            <Button variant="secondary" onClick={test}
              disabled={testing || !configured} icon={ShieldCheck}>
              Test connection
            </Button>
          </div>
        </div>

        {form.dygine_key_secret_set && !form.dygine_key_secret_readable && (
          <InlineAlert variant="danger">
            The stored key secret cannot be decrypted — it was saved with a
            different encryption key. Re-enter it.
          </InlineAlert>
        )}

        {configured && !form.dygine_webhook_secret_set && (
          <InlineAlert variant="warning">
            No webhook secret. Payments will still be taken, but this app will
            never hear that they succeeded, so subscriptions will not extend on
            their own. Set one here and the same value on the webhook in Dygine
            admin.
          </InlineAlert>
        )}

        <div className="pt-3 border-t">
          <p className="text-xs text-muted mb-1.5">
            Point the Dygine webhook for this product at:
          </p>
          <code className="block text-xs bg-slate-50 rounded px-2.5 py-2 break-all">
            {`<your API origin>/api/v1/webhooks/dygine`}
          </code>
        </div>

        <FormField
          label="Low-balance warning (days before renewal)"
          hint="0 turns the warning off. A silent failure on renewal day is a support ticket; a warning a week early is a top-up."
        >
          <Input type="number" min="0" max="60"
            value={form.wallet_low_balance_warning_days ?? 7}
            onChange={onChange('wallet_low_balance_warning_days')} />
        </FormField>
      </div>
    </Card>
  )
}
