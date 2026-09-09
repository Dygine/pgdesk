import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Building2, Eye, EyeOff, ShieldCheck, Users, BedDouble, Copy } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { Button, FormField, Input, InlineAlert, StatusBadge } from '@/components/ui'
import { useToast } from '@/context/ToastContext'
import { Capacitor } from '@capacitor/core'

/**
 * Whether to offer the seeded development accounts on the sign-in screen.
 *
 * An explicit opt-in rather than `import.meta.env.DEV`, because DEV is false for
 * every `vite build` regardless of --mode: a gate on it is unverifiable, since
 * both a production and a development build strip the branch and the only way
 * to see the other behaviour is to run the dev server. A named variable can be
 * tested in both directions, and a deployer can turn it on for a staging box
 * deliberately instead of discovering the rule by accident.
 *
 * The gate matters because these are working credentials. A login page that
 * lists real accounts and fills in their passwords hands anyone who loads it a
 * valid session on any deployment where the seed has been run. Default off:
 * unset means absent.
 */
const SHOW_SEED_ACCOUNTS = import.meta.env.VITE_SHOW_SEED_ACCOUNTS === 'true'

export default function Login() {
  const { login } = useAuth()
  const { success } = useToast()
  const navigate = useNavigate()
  // Prefilled in development only. In production these are empty strings and
  // the credentials are not in the bundle at all.
  const [email, setEmail] = useState(SHOW_SEED_ACCOUNTS ? 'owner@sunrise.local' : '')
  const [password, setPassword] = useState(SHOW_SEED_ACCOUNTS ? 'Owner@2024' : '')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  /* Seeded by `backend/seed.py`. Development only — see SHOW_SEED_ACCOUNTS. */
  const DEMO_LOGINS = SHOW_SEED_ACCOUNTS ? [
    { email: 'master@pgdesk.local', password: 'Master@2024', label: 'Master Admin',
      sub: 'Platform owner \u00b7 all organisations' },
    { email: 'owner@sunrise.local', password: 'Owner@2024', label: 'PG Owner',
      sub: 'Sunrise Living PG \u00b7 all 3 branches' },
    { email: 'manager@sunrise.local', password: 'Manager@2024', label: 'Branch Manager',
      sub: 'Koramangala + BTM only' },
    { email: 'accounts@sunriselivingpg.com', password: 'demo1234', label: 'Accountant',
      sub: 'Billing and expenses, no operations' },
    { email: 'reception@sunriselivingpg.com', password: 'demo1234', label: 'Receptionist',
      sub: 'Front desk \u00b7 Koramangala' },
    { email: 'security@sunriselivingpg.com', password: 'demo1234', label: 'Security',
      sub: 'Gate duty \u00b7 scanning only' },
    { email: 'customer@sunrise.local', password: 'Customer@2024', label: 'Resident',
      sub: 'A tenant\u2019s own view' },
  ] : []

  /* Real call to POST /api/v1/auth/login. The artificial delay is gone - the
     request supplies its own. */
  const submit = async (e) => {
    e?.preventDefault()
    setError('')
    setBusy(true)
    const res = await login(email, password)
    setBusy(false)
    if (!res.ok) return setError(res.error)
    navigate(res.portal === 'master' ? '/master' : res.portal === 'customer' ? '/me' : '/app')
  }

  const pickAccount = (acct) => {
    setEmail(acct.email)
    setPassword(acct.password)
    setError('')
  }

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      {/* Left: what the product does. No figures — a public page must not
          publish tenant counts, and invented ones would be worse. */}
      <div className="hidden lg:flex flex-col justify-between bg-brand-900 text-white p-12 xl:p-16">
        <div className="flex items-center gap-3">
          <span className="h-10 w-10 rounded-xl bg-white text-brand-900 inline-flex items-center justify-center font-bold">P</span>
          <div>
            <p className="font-semibold leading-tight">PGDesk</p>
            <p className="text-xs text-brand-300">PG &amp; hostel operations</p>
          </div>
        </div>

        <div className="max-w-md">
          <h1 className="text-[2.6rem] leading-[1.1] font-semibold tracking-[-0.02em]">
            Every bed, every rupee, every branch — on one screen.
          </h1>
          <p className="mt-5 text-brand-200 leading-relaxed">
            Built for PG and hostel owners in India who are still running three branches
            out of a notebook and four WhatsApp groups.
          </p>

          <dl className="mt-10 grid grid-cols-3 gap-6">
            {[
              { icon: Building2, t: 'Multi-branch', l: 'One account across every property you run' },
              { icon: BedDouble, t: 'Bed-level', l: 'Occupancy tracked down to the individual bed' },
              { icon: Users, t: 'Resident portal', l: 'Rent, complaints and gate passes, self-service' },
            ].map((s) => (
              <div key={s.t}>
                <s.icon size={18} className="text-brand-400 mb-2" />
                <dt className="text-base font-semibold">{s.t}</dt>
                <dd className="text-xs text-brand-300 mt-1 leading-snug">{s.l}</dd>
              </div>
            ))}
          </dl>
        </div>

        <p className="text-xs text-brand-400 flex items-center gap-2">
          <ShieldCheck size={14} />
          Your session is protected. Report anything unexpected to your administrator.
        </p>
      </div>

      {/* Right: sign in */}
      <div className="flex flex-col justify-center px-5 sm:px-8 lg:px-14 py-10 bg-white min-h-screen lg:min-h-0">
        <div className="lg:hidden flex items-center gap-2.5 mb-8">
          <span className="h-9 w-9 rounded-lg bg-brand-800 text-white inline-flex items-center justify-center font-bold text-sm">P</span>
          <div>
            <p className="font-semibold text-slate-900 leading-tight">PGDesk</p>
            <p className="text-xs text-slate-500">PG &amp; hostel operations</p>
          </div>
        </div>

        <div className="w-full max-w-sm mx-auto lg:mx-0">
          <h2 className="text-2xl font-semibold text-slate-900">Sign in</h2>
          <p className="text-sm text-slate-500 mt-1.5">Sign in with your PGDesk account.</p>

          <form onSubmit={submit} className="mt-7 space-y-4">
            <FormField label="Email address" htmlFor="email" required>
              <Input id="email" type="email" value={email} autoComplete="username"
                onChange={(e) => setEmail(e.target.value)} placeholder="you@yourpg.com" />
            </FormField>

            <FormField label="Password" htmlFor="password" required>
              <div className="relative">
                <Input id="password" type={show ? 'text' : 'password'} value={password} autoComplete="current-password"
                  onChange={(e) => setPassword(e.target.value)} className="pr-10" />
                <button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? 'Hide password' : 'Show password'}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700">
                  {show ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </FormField>

            {error && <InlineAlert tone="error">{error}</InlineAlert>}

            <Button type="submit" variant="primary" size="lg" loading={busy} iconRight={ArrowRight} className="w-full">
              Sign in
            </Button>
          </form>

                  {/* Web only. Inside the APK this screen is already the app, so the
            download prompt would be nonsense there. */}
        {!Capacitor.isNativePlatform() && (
          <a href="https://get.dygine.com"
            className="mt-8 flex items-center gap-3 rounded-lg border border-line px-3.5 py-3 hover:bg-slate-50 transition-colors">
            <span className="h-9 w-9 rounded-lg bg-brand-800 text-white inline-flex items-center justify-center font-bold text-sm shrink-0">P</span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium text-slate-900">Get the Android app</span>
              <span className="block text-xs text-slate-500">Same account, on your phone</span>
            </span>
            <span className="text-slate-400 shrink-0" aria-hidden="true">›</span>
          </a>
        )}

          {SHOW_SEED_ACCOUNTS && (
          <div className="mt-8">
            <div className="flex items-center gap-3">
              <span className="h-px flex-1 bg-line" />
              <span className="text-xs text-slate-400">Development accounts</span>
              <span className="h-px flex-1 bg-line" />
            </div>

            <div className="mt-4 space-y-1.5">
              {DEMO_LOGINS.map((a) => {
                const selected = email === a.email
                return (
                  <button key={a.label} onClick={() => pickAccount(a)} type="button"
                    className={`w-full flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
                      selected ? 'border-brand-300 bg-brand-50' : 'border-line hover:bg-slate-50'}`}>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-900">{a.label}</p>
                      <p className="text-xs text-slate-500 truncate">{a.sub}</p>
                    </div>
                    {selected && <StatusBadge status="Selected" tone="brand" />}
                  </button>
                )
              })}
            </div>

            <div className="mt-4 flex items-center justify-between gap-2 rounded-lg bg-slate-50 border border-line px-3 py-2.5">
              <p className="text-xs text-slate-600">
                Choosing an account fills its password in.{' '}
                <span className="font-mono font-medium text-slate-900">{password || '\u2014'}</span>
              </p>
              <button type="button"
                onClick={() => { navigator.clipboard?.writeText(password); success('Password copied') }}
                className="text-slate-400 hover:text-slate-700 shrink-0" aria-label="Copy password">
                <Copy size={14} />
              </button>
            </div>
          </div>
          )}
        </div>
      </div>
    </div>
  )
}
