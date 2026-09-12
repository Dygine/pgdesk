/**
 * A resident's app access, and editing their details.
 *
 * Both used to be missing from the profile. A resident added without the
 * "portal login" tick could never be given one afterwards, and there was no
 * way to add the email that a login needs - the edit endpoint did not even
 * accept one. This card and modal are that way.
 */
import { useEffect, useState } from 'react'
import { QrCode as QrIcon, KeyRound, ShieldOff } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { residentApi } from '@/services/api/residentApi'
import { PortalCredentials } from '@/components/domain'
import {
  Card, CardHeader, Button, StatusBadge, Modal, FormField, Input, Select, Textarea,
  ConfirmDialog, InlineAlert,
} from '@/components/ui'
import { relative } from '@/lib/format'

const EMAIL = /^\S+@\S+\.\S+$/

/* ------------------------------------------------------------- access card */
export function PortalAccessCard({ resident: r, onChanged }) {
  const { can } = useAuth()
  const { success, error } = useToast()
  const [creds, setCreds] = useState(null)
  const [busy, setBusy] = useState(null)
  const [askEmail, setAskEmail] = useState(false)
  const [email, setEmail] = useState('')
  const [emailError, setEmailError] = useState(null)
  const [confirm, setConfirm] = useState(null)       // 'reset' | 'off'

  const canEdit = can('customers.edit')
  const gone = r.status === 'CHECKED_OUT' || r.is_active === false
  const hasLogin = !!r.has_portal_login
  const pending = hasLogin && !!r.must_change_password

  const run = async (key, fn, message) => {
    setBusy(key)
    try {
      const data = await fn()
      if (data?.credentials) setCreds(data.credentials)
      success(message)
      onChanged?.()
      return true
    } catch (err) {
      error('That did not work', err.message)
      return false
    } finally { setBusy(null) }
  }

  const give = () => {
    if (!r.email) { setEmail(''); setEmailError(null); setAskEmail(true); return }
    run('give', () => residentApi.grantPortalAccess(r.id), 'App access given')
  }

  const giveWithEmail = async () => {
    const value = email.trim()
    if (!EMAIL.test(value)) { setEmailError('Enter a valid email address.'); return }
    if (await run('give', () => residentApi.grantPortalAccess(r.id, value), 'App access given')) {
      setAskEmail(false)
    }
  }

  // Offered when a QR expires. Keeps the temporary password already shown.
  const renew = async (prev) => {
    const data = await residentApi.loginCode(r.id)
    return { ...prev, ...data.credentials }
  }

  const state = gone
    ? { label: 'Checked out', tone: 'slate', text: 'Checked-out residents cannot sign in.' }
    : !hasLogin
      ? { label: 'Not set up', tone: 'amber',
          text: r.email ? `Give them access and they sign in as ${r.email}.`
            : 'Add their email, then give access. The email becomes their sign-in ID.' }
      : pending
        ? { label: 'Waiting for first sign-in', tone: 'blue',
            text: 'They have not chosen their own password yet. Show them a sign-in QR to finish.' }
        : { label: 'Active', tone: 'emerald',
            text: r.last_login_at ? `Last signed in ${relative(r.last_login_at)}.`
              : 'They have chosen their own password.' }

  return (
    <Card>
      <CardHeader title="App access" subtitle="How this resident signs in to the PGuru app"
        action={<StatusBadge status={state.label} tone={state.tone} dot />} />
      <div className="px-5 py-4 space-y-1">
        <p className="text-sm text-slate-600">{state.text}</p>
        {hasLogin && r.email && (
          <p className="text-xs text-slate-500">
            Sign-in ID <span className="font-mono text-slate-700">{r.email}</span>
          </p>
        )}
      </div>

      {canEdit && !gone && (
        <div className="px-5 py-4 border-t border-line flex flex-wrap gap-2">
          {!hasLogin && (
            <Button variant="primary" size="sm" icon={QrIcon} loading={busy === 'give'}
              onClick={give}>Give app access</Button>
          )}
          {pending && (
            <Button variant="primary" size="sm" icon={QrIcon} loading={busy === 'qr'}
              onClick={() => run('qr', () => residentApi.loginCode(r.id), 'Sign-in QR ready')}>
              Show sign-in QR
            </Button>
          )}
          {hasLogin && (
            <Button size="sm" icon={KeyRound} loading={busy === 'reset'}
              onClick={() => setConfirm('reset')}>Reset password</Button>
          )}
          {hasLogin && (
            <Button size="sm" icon={ShieldOff} loading={busy === 'off'}
              onClick={() => setConfirm('off')}>Turn off</Button>
          )}
        </div>
      )}

      <PortalCredentials open={!!creds} onClose={() => setCreds(null)} name={r.full_name}
        credentials={creds} onRenew={renew} />

      <Modal open={askEmail} onClose={() => setAskEmail(false)} size="sm" title="Add their email"
        subtitle="It becomes their sign-in ID for the app."
        footer={<><Button onClick={() => setAskEmail(false)}>Cancel</Button>
          <Button variant="primary" loading={busy === 'give'} onClick={giveWithEmail}>
            Save and give access</Button></>}>
        <FormField label="Email" required error={emailError}>
          <Input type="email" value={email} autoFocus error={emailError}
            onChange={(e) => { setEmail(e.target.value); setEmailError(null) }}
            onKeyDown={(e) => e.key === 'Enter' && giveWithEmail()} />
        </FormField>
      </Modal>

      <ConfirmDialog open={confirm === 'reset'} onClose={() => setConfirm(null)}
        onConfirm={() => run('reset', () => residentApi.resetPortalPassword(r.id),
          'New sign-in details issued')}
        title="Reset their password?" confirmLabel="Reset password"
        message="Their current password stops working and they are signed out of the app. You get a new temporary password and sign-in QR to give them." />
      <ConfirmDialog open={confirm === 'off'} onClose={() => setConfirm(null)}
        onConfirm={() => run('off', () => residentApi.revokePortalAccess(r.id),
          'App access turned off')}
        title="Turn off app access?" confirmLabel="Turn off"
        message="They are signed out and cannot sign in until you give access again. Their records stay as they are." />
    </Card>
  )
}

/* -------------------------------------------------------------- edit modal */
const blank = (v) => (v == null ? '' : String(v))

export function EditResidentModal({ resident: r, open, onClose, onSaved }) {
  const { success, error } = useToast()
  const [f, setF] = useState({})
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open || !r) return
    const [first, ...rest] = (r.full_name || '').split(' ')
    setF({
      first_name: r.first_name || first || '', last_name: r.last_name ?? rest.join(' '),
      phone: blank(r.phone), alternate_phone: blank(r.alternate_phone), email: blank(r.email),
      gender: blank(r.gender), date_of_birth: blank(r.date_of_birth), occupation: blank(r.occupation),
      address: blank(r.address), city: blank(r.city), state: blank(r.state), pincode: blank(r.pincode),
      emergency_contact_name: blank(r.emergency_contact_name),
      emergency_contact_phone: blank(r.emergency_contact_phone),
      emergency_contact_relation: blank(r.emergency_contact_relation),
      monthly_rent: blank(r.monthly_rent), security_deposit: blank(r.security_deposit),
      rent_due_day: blank(r.rent_due_day || 5),
      expected_checkout_date: blank(r.expected_checkout_date), notes: blank(r.notes),
    })
    setErrs({})
  }, [open, r])

  if (!r) return null
  const set = (k) => (e) => {
    setF((x) => ({ ...x, [k]: e.target.value }))
    setErrs((x) => ({ ...x, [k]: undefined }))
  }

  const save = async () => {
    const e = {}
    if (!f.first_name.trim()) e.first_name = 'Enter a first name.'
    if (!/^[\d\s+\-()]{6,}$/.test(f.phone)) e.phone = 'Enter a valid phone number.'
    if (f.email.trim() && !EMAIL.test(f.email.trim())) e.email = 'Enter a valid email address.'
    if (r.has_portal_login && !f.email.trim()) {
      e.email = 'They sign in with this email. Turn off app access before removing it.'
    }
    const due = Number(f.rent_due_day)
    if (!(due >= 1 && due <= 28)) e.rent_due_day = 'Pick a day from 1 to 28.'
    setErrs(e)
    if (Object.keys(e).length) return

    setBusy(true)
    try {
      await residentApi.update(r.id, {
        first_name: f.first_name.trim(), last_name: f.last_name.trim(),
        full_name: `${f.first_name} ${f.last_name}`.trim().replace(/\s+/g, ' '),
        phone: f.phone.trim(), alternate_phone: f.alternate_phone.trim(),
        email: f.email.trim() || null,
        gender: f.gender, date_of_birth: f.date_of_birth || null,
        occupation: f.occupation.trim(), address: f.address.trim(), city: f.city.trim(),
        state: f.state.trim(), pincode: f.pincode.trim(),
        emergency_contact_name: f.emergency_contact_name.trim(),
        emergency_contact_phone: f.emergency_contact_phone.trim(),
        emergency_contact_relation: f.emergency_contact_relation.trim(),
        // Blank money fields are left alone rather than sent as zero.
        monthly_rent: f.monthly_rent === '' ? undefined : Number(f.monthly_rent),
        security_deposit: f.security_deposit === '' ? undefined : Number(f.security_deposit),
        rent_due_day: due,
        expected_checkout_date: f.expected_checkout_date || null,
        notes: f.notes,
      })
      success('Resident updated')
      onSaved?.()
    } catch (err) {
      error('Could not save', err.message)
      if (Object.keys(err.fieldErrors || {}).length) setErrs(err.fieldErrors)
    } finally { setBusy(false) }
  }

  return (
    <Modal open={open} onClose={onClose} size="lg" title={`Edit ${r.full_name}`}
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} onClick={save}>Save changes</Button></>}>
      <div className="space-y-5">
        <div className="grid sm:grid-cols-2 gap-4">
          <FormField label="First name" required error={errs.first_name}>
            <Input value={f.first_name || ''} onChange={set('first_name')} error={errs.first_name} />
          </FormField>
          <FormField label="Last name">
            <Input value={f.last_name || ''} onChange={set('last_name')} />
          </FormField>
          <FormField label="Phone" required error={errs.phone}>
            <Input value={f.phone || ''} onChange={set('phone')} inputMode="tel" error={errs.phone} />
          </FormField>
          <FormField label="Email" required={!!r.has_portal_login} error={errs.email}
            hint={r.has_portal_login ? 'Their sign-in ID for the app.'
              : 'Add one to give them app access.'}>
            <Input type="email" value={f.email || ''} onChange={set('email')} error={errs.email} />
          </FormField>
          <FormField label="Alternate phone">
            <Input value={f.alternate_phone || ''} onChange={set('alternate_phone')} inputMode="tel" />
          </FormField>
          <FormField label="Gender">
            <Select value={f.gender || ''} onChange={set('gender')}>
              <option value="">Not specified</option>
              {['Male', 'Female', 'Other'].map((x) => <option key={x}>{x}</option>)}
            </Select>
          </FormField>
          <FormField label="Date of birth">
            <Input type="date" value={f.date_of_birth || ''} onChange={set('date_of_birth')} />
          </FormField>
          <FormField label="Occupation">
            <Input value={f.occupation || ''} onChange={set('occupation')} />
          </FormField>
        </div>

        <div>
          <p className="text-[13px] font-semibold text-slate-800 mb-3 pb-2 border-b border-line">Address</p>
          <div className="grid sm:grid-cols-2 gap-4">
            <FormField label="Address" className="sm:col-span-2">
              <Input value={f.address || ''} onChange={set('address')} />
            </FormField>
            <FormField label="City"><Input value={f.city || ''} onChange={set('city')} /></FormField>
            <FormField label="State"><Input value={f.state || ''} onChange={set('state')} /></FormField>
            <FormField label="Pincode">
              <Input value={f.pincode || ''} onChange={set('pincode')} inputMode="numeric" />
            </FormField>
          </div>
        </div>

        <div>
          <p className="text-[13px] font-semibold text-slate-800 mb-3 pb-2 border-b border-line">Money</p>
          <div className="grid sm:grid-cols-3 gap-4">
            <FormField label="Monthly rent">
              <Input inputMode="numeric" className="tnum" value={f.monthly_rent || ''}
                onChange={set('monthly_rent')} />
            </FormField>
            <FormField label="Security deposit">
              <Input inputMode="numeric" className="tnum" value={f.security_deposit || ''}
                onChange={set('security_deposit')} />
            </FormField>
            <FormField label="Rent due day" error={errs.rent_due_day} hint="1 to 28">
              <Input inputMode="numeric" className="tnum" value={f.rent_due_day || ''}
                onChange={set('rent_due_day')} error={errs.rent_due_day} />
            </FormField>
            <FormField label="Expected checkout">
              <Input type="date" value={f.expected_checkout_date || ''}
                onChange={set('expected_checkout_date')} />
            </FormField>
          </div>
        </div>

        <div>
          <p className="text-[13px] font-semibold text-slate-800 mb-3 pb-2 border-b border-line">Emergency contact</p>
          <div className="grid sm:grid-cols-3 gap-4">
            <FormField label="Name">
              <Input value={f.emergency_contact_name || ''} onChange={set('emergency_contact_name')} />
            </FormField>
            <FormField label="Phone">
              <Input value={f.emergency_contact_phone || ''} onChange={set('emergency_contact_phone')} />
            </FormField>
            <FormField label="Relation">
              <Input value={f.emergency_contact_relation || ''}
                onChange={set('emergency_contact_relation')} />
            </FormField>
          </div>
        </div>

        <FormField label="Notes">
          <Textarea value={f.notes || ''} onChange={set('notes')} rows={3} />
        </FormField>
        {r.has_portal_login && (
          <InlineAlert tone="info">
            Changing the email changes what they type to sign in. Let them know.
          </InlineAlert>
        )}
      </div>
    </Modal>
  )
}
