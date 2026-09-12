import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Building2, Search, ArrowLeft, ArrowRight, Mail, CheckCircle2, ShieldCheck,
} from 'lucide-react'
import { publicApi } from '@/services/api/publicApi'
import { Card, Button, FormField, Input, InlineAlert, BrandLogo } from '@/components/ui'

/**
 * Public signup.
 *
 * Two audiences with almost nothing in common, so the first question is which
 * one you are, and the paths diverge immediately:
 *
 *   PG owner   verifies an email, then creates an organisation with a free
 *              trial. A real account.
 *   Looking    verifies an email, then browses listings and sends enquiries.
 *              No account at all.
 *
 * The second one surprises people, so the screen says it plainly rather than
 * letting someone fill in a password field that leads nowhere. A person hunting
 * for a PG belongs to no organisation, and every login in this system is scoped
 * to one - so their interaction is an enquiry, and the PG creates their
 * resident account when they actually move in.
 *
 * Email is proved before anything is created. Without that this page is a way
 * to register unlimited organisations under other people's addresses.
 */
export default function Signup() {
  const navigate = useNavigate()
  const [role, setRole] = useState(null)          // 'owner' | 'seeker'
  const [step, setStep] = useState('email')       // email | code | details | done
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [token, setToken] = useState(null)
  const [form, setForm] = useState({
    pg_name: '', owner_name: '', phone: '', city: 'Bengaluru',
    password: '', confirm: '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const sendCode = async () => {
    setBusy(true); setError(null)
    try {
      await publicApi.sendCode(email.trim())
      setStep('code')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const checkCode = async () => {
    setBusy(true); setError(null)
    try {
      const res = await publicApi.verifyCode(email.trim(), code.trim())
      setToken(res.verification_token)
      // A verified seeker has nothing left to fill in - the token is what the
      // enquiry form needs, and it travels with them to the search page.
      if (role === 'seeker') {
        navigate('/find-pg', {
          state: { verifiedEmail: email.trim().toLowerCase(),
                   verificationToken: res.verification_token },
        })
        return
      }
      setStep('details')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const createAccount = async () => {
    if (form.password !== form.confirm) return setError('The two passwords do not match.')
    if (form.password.length < 8) return setError('Use at least 8 characters.')
    setBusy(true); setError(null)
    try {
      const res = await publicApi.signupOwner({
        verification_token: token,
        pg_name: form.pg_name.trim(),
        owner_name: form.owner_name.trim(),
        phone: form.phone.trim() || null,
        city: form.city.trim() || null,
        password: form.password,
      })
      setResult(res)
      setStep('done')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  /* ------------------------------------------------------------ chooser */
  if (!role) {
    return (
      <Shell>
        <h1 className="text-lg font-semibold text-slate-900">Get started</h1>
        <p className="text-sm text-slate-500 mt-1 mb-6">Which one are you?</p>

        <button type="button" onClick={() => setRole('owner')}
          className="w-full text-left rounded-xl border border-line p-4 hover:border-brand-400
                     hover:bg-brand-50/40 transition-colors mb-3">
          <div className="flex items-start gap-3">
            <span className="h-10 w-10 rounded-xl bg-brand-50 text-brand-700
                             inline-flex items-center justify-center shrink-0">
              <Building2 size={18} />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-slate-900">I run a PG</p>
              <p className="text-xs text-slate-500 mt-0.5">
                Manage rooms, residents, rent and complaints. Free for 30 days,
                no card needed.
              </p>
            </div>
            <ArrowRight size={16} className="text-slate-300 mt-1 shrink-0" />
          </div>
        </button>

        <button type="button"
          onClick={() => navigate('/find-pg', { state: { openAuth: 'signup' } })}
          className="w-full text-left rounded-xl border border-line p-4 hover:border-brand-400
                     hover:bg-brand-50/40 transition-colors">
          <div className="flex items-start gap-3">
            <span className="h-10 w-10 rounded-xl bg-violet-50 text-violet-700
                             inline-flex items-center justify-center shrink-0">
              <Search size={18} />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-slate-900">I am looking for a PG</p>
              <p className="text-xs text-slate-500 mt-0.5">
                Free account. See PGs with free beds near you and enquire in
                one tap.
              </p>
            </div>
            <ArrowRight size={16} className="text-slate-300 mt-1 shrink-0" />
          </div>
        </button>

        <p className="text-xs text-slate-500 text-center mt-6">
          Already have an account?{' '}
          <Link to="/login" className="text-brand-700 hover:text-brand-800">Sign in</Link>
        </p>
      </Shell>
    )
  }

  /* --------------------------------------------------------------- steps */
  return (
    <Shell onBack={() => {
      if (step === 'email') { setRole(null); setError(null) }
      else { setStep('email'); setCode(''); setError(null) }
    }}>
      {step === 'email' && (
        <>
          <h1 className="text-lg font-semibold text-slate-900">
            {role === 'owner' ? 'Create your PG account' : 'Find a PG'}
          </h1>
          <p className="text-sm text-slate-500 mt-1 mb-6">
            {role === 'owner'
              ? 'We will email you a code to confirm the address.'
              : 'Confirm your email so PGs know an enquiry is genuine.'}
          </p>
          {error && <InlineAlert tone="error" className="mb-4">{error}</InlineAlert>}
          <FormField label="Email address">
            <Input type="email" value={email} autoFocus autoComplete="email"
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && email.trim() && sendCode()}
              placeholder="you@example.com" />
          </FormField>
          <Button variant="primary" icon={Mail} className="w-full mt-5"
            loading={busy} disabled={!email.includes('@')} onClick={sendCode}>
            Send me a code
          </Button>
        </>
      )}

      {step === 'code' && (
        <>
          <h1 className="text-lg font-semibold text-slate-900">Enter the code</h1>
          <p className="text-sm text-slate-500 mt-1 mb-6">
            We sent a 6-digit code to {email}. It expires in 10 minutes.
          </p>
          {error && <InlineAlert tone="error" className="mb-4">{error}</InlineAlert>}
          <FormField label="Verification code" hint="Check your spam folder if it has not arrived.">
            <Input value={code} autoFocus inputMode="numeric" maxLength={6}
              autoComplete="one-time-code"
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              onKeyDown={(e) => e.key === 'Enter' && code.length === 6 && checkCode()}
              className="tnum text-center text-xl tracking-[0.5em]" placeholder="000000" />
          </FormField>
          <Button variant="primary" icon={ShieldCheck} className="w-full mt-5"
            loading={busy} disabled={code.length < 4} onClick={checkCode}>
            Verify email
          </Button>
        </>
      )}

      {step === 'details' && (
        <>
          <h1 className="text-lg font-semibold text-slate-900">About your PG</h1>
          <p className="text-sm text-slate-500 mt-1 mb-6">
            You can change any of this later.
          </p>
          {error && <InlineAlert tone="error" className="mb-4">{error}</InlineAlert>}
          <div className="space-y-4">
            <FormField label="PG name" required>
              <Input value={form.pg_name} autoFocus onChange={set('pg_name')}
                placeholder="Sunrise Living PG" />
            </FormField>
            <div className="grid sm:grid-cols-2 gap-4">
              <FormField label="Your name" required>
                <Input value={form.owner_name} onChange={set('owner_name')} />
              </FormField>
              <FormField label="Phone">
                <Input value={form.phone} onChange={set('phone')} inputMode="tel" />
              </FormField>
            </div>
            <FormField label="City">
              <Input value={form.city} onChange={set('city')} />
            </FormField>
            <div className="grid sm:grid-cols-2 gap-4">
              <FormField label="Password" required hint="At least 8 characters.">
                <Input type="password" value={form.password} autoComplete="new-password"
                  onChange={set('password')} />
              </FormField>
              <FormField label="Confirm password" required>
                <Input type="password" value={form.confirm} autoComplete="new-password"
                  onChange={set('confirm')} />
              </FormField>
            </div>
          </div>
          <Button variant="primary" className="w-full mt-5" loading={busy}
            disabled={!form.pg_name.trim() || !form.owner_name.trim() || !form.password}
            onClick={createAccount}>
            Start my 30-day free trial
          </Button>
          <p className="text-2xs text-slate-500 text-center mt-3">
            No card required. Nothing is charged when the trial ends — the
            account becomes read-only until you choose a plan.
          </p>
        </>
      )}

      {step === 'done' && (
        <div className="text-center py-4">
          <CheckCircle2 size={34} className="mx-auto text-emerald-600 mb-3" />
          <h1 className="text-lg font-semibold text-slate-900">
            {result?.organization} is ready
          </h1>
          <p className="text-sm text-slate-500 mt-1 mb-6">
            Your {result?.trial_days}-day free trial has started. Sign in and add
            your first branch.
          </p>
          <Button variant="primary" className="w-full" onClick={() => navigate('/login')}>
            Sign in
          </Button>
        </div>
      )}
    </Shell>
  )
}

function Shell({ children, onBack }) {
  return (
    <div className="min-h-dvh flex items-center justify-center p-4 bg-slate-50">
      <Card className="w-full max-w-lg">
        <div className="p-6 sm:p-8">
          <BrandLogo className="h-10 w-auto mb-5" />
          {onBack ? (
            <button type="button" onClick={onBack}
              className="inline-flex items-center gap-1.5 text-xs text-slate-500
                         hover:text-slate-800 mb-5">
              <ArrowLeft size={13} /> Back
            </button>
          ) : (
            <Link to="/login"
              className="inline-flex items-center gap-1.5 text-xs text-slate-500
                         hover:text-slate-800 mb-5">
              <ArrowLeft size={13} /> Back to sign in
            </Link>
          )}
          {children}
        </div>
      </Card>
    </div>
  )
}
