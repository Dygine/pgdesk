import { useEffect, useState } from 'react'
import { Mail, Send, CircleCheck, CircleAlert, KeyRound } from 'lucide-react'
import {
  Card, CardHeader, FormField, Input, Select, Button, Toggle, InlineAlert,
} from '@/components/ui'
import { useToast } from '@/context/ToastContext'
import { platformSettingsApi } from '@/services/api/platformSettingsApi'

/**
 * The mail server.
 *
 * Two things this card is careful about.
 *
 * The password is write-only. The API never returns it, so the field starts
 * empty even when one is stored, and leaving it empty on save means "keep the
 * existing one". A form that pre-filled a secret would be a way to read
 * secrets, which is the opposite of what storing it encrypted is for.
 *
 * "Saved" and "delivers" are shown as separate facts. A wrong port, or a Gmail
 * account password where an app password was needed, both save perfectly and
 * send nothing - so there is a test button, and the verified badge only lights
 * up after a message actually left the building.
 */
export function SmtpCard({ form, onChange, onSaved }) {
  const { success, error } = useToast()
  const [password, setPassword] = useState('')
  const [testTo, setTestTo] = useState('')
  const [busy, setBusy] = useState(null)

  useEffect(() => { setTestTo(form?.support_email || '') }, [form?.support_email])

  if (!form) return null

  const provider = form.email_provider || 'smtp'
  const isBrevo = provider === 'brevo'
  const fromEnv = form.channels?.email?.source === 'environment'
  const verified = isBrevo ? !!form.brevo_verified_at : !!form.smtp_verified_at
  const stored = isBrevo ? !!form.brevo_api_key_set : !!form.smtp_password_set

  const savePassword = async () => {
    setBusy('password')
    try {
      const data = isBrevo
        ? await platformSettingsApi.setBrevoKey(password)
        : await platformSettingsApi.setSmtpPassword(password)
      setPassword('')
      onSaved?.(data)
      success(isBrevo ? 'Brevo key saved' : 'Mail password saved',
        'Send a test message to confirm it works.')
    } catch (err) {
      error('Could not save the password', err.message)
    } finally { setBusy(null) }
  }

  const sendTest = async () => {
    setBusy('test')
    try {
      const data = await platformSettingsApi.sendTestEmail(testTo.trim())
      onSaved?.(data)
      success('Test message delivered', `Check the inbox for ${testTo.trim()}.`)
    } catch (err) {
      // The SMTP error verbatim. The caller is a master admin who owns these
      // credentials, and a generic "could not send" would leave them guessing
      // between six causes that all look identical from outside.
      error('The test message did not send', err.message)
    } finally { setBusy(null) }
  }

  return (
    <Card>
      <CardHeader title="Email"
        subtitle="Used for password resets and verification codes."
        action={verified
          ? <span className="inline-flex items-center gap-1.5 text-xs text-emerald-700">
              <CircleCheck size={13} /> Delivery confirmed</span>
          : <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
              <CircleAlert size={13} /> Not yet tested</span>} />

      <div className="p-5 space-y-4">
        {isBrevo && !form.brevo_api_key_set && !fromEnv && (
          <InlineAlert tone="warn" title="No Brevo key yet">
            Password resets and signup codes cannot be delivered until a key is
            saved. Both flows will accept the request and silently send nothing.
          </InlineAlert>
        )}

        {fromEnv && (
          <InlineAlert tone="info" title="Configured in the environment">
            Credentials are set on the server, and those values win over anything
            entered here. Clear them from the environment if you want to manage
            mail from this screen instead.
          </InlineAlert>
        )}

        {!isBrevo && !form.smtp_host && !fromEnv && (
          <InlineAlert tone="warn" title="No mail server yet">
            Password resets and signup codes cannot be delivered until this is
            filled in. Both flows will accept the request and silently send
            nothing.
          </InlineAlert>
        )}

        <FormField label="How email is sent"
          hint={isBrevo
            ? 'Brevo posts over https on port 443, which no host blocks. Use this on Render, Railway, Vercel and anywhere else that closes SMTP ports.'
            : 'A direct connection to a mail server on port 587. Many managed hosts block that port on free plans — if test messages cannot reach the server, switch to Brevo.'}>
          <Select value={provider} onChange={onChange('email_provider')}>
            <option value="smtp">SMTP server (Gmail, your own mail host)</option>
            <option value="brevo">Brevo API (recommended)</option>
          </Select>
        </FormField>

        {isBrevo ? (
          <>
            <div className="grid sm:grid-cols-2 gap-4">
              <FormField label="Sender address" required
                hint="Must be verified in Brevo under Senders, domains, IPs.">
                <Input value={form.brevo_sender_email || ''}
                  onChange={onChange('brevo_sender_email')}
                  placeholder="no-reply@yourdomain.com" disabled={fromEnv} />
              </FormField>
              <FormField label="Sender name"
                hint="What residents see the message came from.">
                <Input value={form.brevo_sender_name || ''}
                  onChange={onChange('brevo_sender_name')}
                  placeholder={form.platform_name || 'PGDesk'} disabled={fromEnv} />
              </FormField>
            </div>

            <FormField label={stored ? 'Change API key' : 'API key'}
              hint={stored
                ? 'A key is stored. Leave blank to keep it.'
                : 'From Brevo: SMTP & API → API Keys. Starts with xkeysib-.'}>
              <div className="flex gap-2">
                <Input type="password" value={password} autoComplete="new-password"
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={stored ? '••••••••••••' : 'xkeysib-…'} disabled={fromEnv} />
                <Button icon={KeyRound} loading={busy === 'password'}
                  disabled={fromEnv || !password} onClick={savePassword}>Save</Button>
              </div>
            </FormField>

            {stored && !form.brevo_api_key_readable && (
              <InlineAlert tone="error" title="The stored key cannot be read">
                It was encrypted with a different SECRET_KEY than the one running
                now. Enter it again to restore email.
              </InlineAlert>
            )}
          </>
        ) : (
        <>
        <div className="grid sm:grid-cols-3 gap-4">
          <FormField label="Host" className="sm:col-span-2">
            <Input value={form.smtp_host || ''} onChange={onChange('smtp_host')}
              placeholder="smtp.gmail.com" disabled={fromEnv} />
          </FormField>
          <FormField label="Port">
            <Input type="number" value={form.smtp_port ?? 587}
              onChange={onChange('smtp_port')} className="tnum" disabled={fromEnv} />
          </FormField>
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <FormField label="Username" hint="Usually the full email address.">
            <Input value={form.smtp_username || ''} onChange={onChange('smtp_username')}
              autoComplete="off" disabled={fromEnv} />
          </FormField>
          <FormField label={stored ? 'Change password' : 'Password'}
            hint={stored
              ? 'A password is stored. Leave blank to keep it.'
              : 'Gmail needs an app password, not your account password.'}>
            <div className="flex gap-2">
              <Input type="password" value={password} autoComplete="new-password"
                onChange={(e) => setPassword(e.target.value)}
                placeholder={stored ? '••••••••••••' : ''} disabled={fromEnv} />
              <Button icon={KeyRound} loading={busy === 'password'}
                disabled={fromEnv || !password} onClick={savePassword}>Save</Button>
            </div>
          </FormField>
        </div>

        {stored && !form.smtp_password_readable && (
          <InlineAlert tone="error" title="The stored password cannot be read">
            It was encrypted with a different SECRET_KEY than the one running
            now. Enter it again to fix mail delivery.
          </InlineAlert>
        )}

        <div className="grid sm:grid-cols-2 gap-4">
          <FormField label="From address" hint="What recipients see it came from.">
            <Input value={form.smtp_from_email || ''} onChange={onChange('smtp_from_email')}
              placeholder="no-reply@yourpg.com" disabled={fromEnv} />
          </FormField>
          <FormField label="From name">
            <Input value={form.smtp_from_name || ''} onChange={onChange('smtp_from_name')}
              placeholder={form.platform_name || 'PGDesk'} disabled={fromEnv} />
          </FormField>
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <FormField label="Encryption"
            hint="STARTTLS on 587 is the usual choice. SSL is for port 465.">
            <Select
              value={form.smtp_use_ssl ? 'ssl' : form.smtp_use_tls ? 'tls' : 'none'}
              disabled={fromEnv}
              onChange={(e) => {
                const v = e.target.value
                onChange('smtp_use_tls')(v === 'tls')
                onChange('smtp_use_ssl')(v === 'ssl')
              }}>
              <option value="tls">STARTTLS (port 587)</option>
              <option value="ssl">SSL/TLS (port 465)</option>
              <option value="none">None (local relay only)</option>
            </Select>
          </FormField>
        </div>

        </>
        )}

        <div className="pt-4 border-t border-line">
          <p className="text-sm font-medium text-slate-800 mb-1">Send a test message</p>
          <p className="text-xs text-slate-500 mb-3">
            Saving is not the same as delivering. This proves the credentials
            actually work before a resident depends on them.
          </p>
          <div className="flex gap-2">
            <Input value={testTo} onChange={(e) => setTestTo(e.target.value)}
              placeholder="you@example.com" type="email" />
            <Button variant="primary" icon={Send} loading={busy === 'test'}
              disabled={!testTo.trim()} onClick={sendTest}>Send test</Button>
          </div>
        </div>
      </div>
    </Card>
  )
}
