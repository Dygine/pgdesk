import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Mail, KeyRound, Lock, ArrowLeft, CheckCircle2 } from 'lucide-react'
import { authApi } from '@/services/api/authApi'
import { Card, Button, FormField, Input, InlineAlert, BrandLogo } from '@/components/ui'

/**
 * Forgotten password, in three steps.
 *
 * The steps are separate because the API keeps them separate: the address is
 * named once, and after that the client carries a token rather than the code,
 * so the code and the new password never travel together.
 *
 * Step one deliberately does not tell the user whether the address exists. That
 * is the API's decision, not this screen's, and the copy has to match it -
 * "check your email" would be a lie for an address with no account, so it says
 * "if that address has an account" instead. It is worth the small awkwardness:
 * the alternative is a free tool for discovering who has an account here.
 */
export default function ForgotPassword() {
  const navigate = useNavigate()
  const [step, setStep] = useState('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [token, setToken] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [note, setNote] = useState(null)

  const sendCode = async () => {
    setBusy(true); setError(null)
    try {
      const res = await authApi.forgotPassword(email.trim())
      setNote(res?.message || null)
      setStep('code')
    } catch (err) {
      setError(err.message)
    } finally { setBusy(false) }
  }

  const checkCode = async () => {
    setBusy(true); setError(null)
    try {
      const res = await authApi.verifyOtp(email.trim(), code.trim())
      setToken(res.verification_token)
      setStep('password')
    } catch (err) {
      setError(err.message)
    } finally { setBusy(false) }
  }

  const save = async () => {
    if (password !== confirm) return setError('The two passwords do not match.')
    if (password.length < 8) return setError('Use at least 8 characters.')
    setBusy(true); setError(null)
    try {
      await authApi.resetPassword(token, password)
      setStep('done')
    } catch (err) {
      setError(err.message)
    } finally { setBusy(false) }
  }

  return (
    <div className="min-h-dvh flex items-center justify-center p-4 bg-slate-50">
      <Card className="w-full max-w-md">
        <div className="p-6 sm:p-8">
          <BrandLogo className="h-10 w-auto mb-5" />
          <Link to="/login"
            className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800 mb-5">
            <ArrowLeft size={13} /> Back to sign in
          </Link>

          {step === 'email' && (
            <>
              <h1 className="text-lg font-semibold text-slate-900">Forgot your password?</h1>
              <p className="text-sm text-slate-500 mt-1 mb-6">
                Enter the email address you sign in with and we will send you a code.
              </p>
              {error && <InlineAlert tone="error" className="mb-4">{error}</InlineAlert>}
              <FormField label="Email address">
                <Input value={email} type="email" autoFocus autoComplete="email"
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && email.trim() && sendCode()}
                  placeholder="you@example.com" />
              </FormField>
              <Button variant="primary" icon={Mail} className="w-full mt-5"
                loading={busy} disabled={!email.trim()} onClick={sendCode}>
                Send me a code
              </Button>
            </>
          )}

          {step === 'code' && (
            <>
              <h1 className="text-lg font-semibold text-slate-900">Enter the code</h1>
              {/* The API's own wording, passed straight through. Rephrasing it
                  here would risk claiming an email was sent to an address that
                  has no account. */}
              <p className="text-sm text-slate-500 mt-1 mb-6">{note}</p>
              {error && <InlineAlert tone="error" className="mb-4">{error}</InlineAlert>}
              <FormField label="6-digit code" hint="Check your spam folder if it has not arrived.">
                <Input value={code} autoFocus inputMode="numeric" maxLength={6}
                  autoComplete="one-time-code"
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                  onKeyDown={(e) => e.key === 'Enter' && code.length === 6 && checkCode()}
                  className="tnum text-center text-xl tracking-[0.5em]" placeholder="000000" />
              </FormField>
              <Button variant="primary" icon={KeyRound} className="w-full mt-5"
                loading={busy} disabled={code.length < 4} onClick={checkCode}>
                Verify code
              </Button>
              <button type="button" onClick={() => { setStep('email'); setCode('') }}
                className="w-full text-xs text-slate-500 hover:text-slate-800 mt-4">
                Use a different email address
              </button>
            </>
          )}

          {step === 'password' && (
            <>
              <h1 className="text-lg font-semibold text-slate-900">Choose a new password</h1>
              <p className="text-sm text-slate-500 mt-1 mb-6">
                You will be signed out everywhere else.
              </p>
              {error && <InlineAlert tone="error" className="mb-4">{error}</InlineAlert>}
              <FormField label="New password" hint="At least 8 characters.">
                <Input type="password" value={password} autoFocus autoComplete="new-password"
                  onChange={(e) => setPassword(e.target.value)} />
              </FormField>
              <FormField label="Confirm password" className="mt-4">
                <Input type="password" value={confirm} autoComplete="new-password"
                  onChange={(e) => setConfirm(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && save()} />
              </FormField>
              <Button variant="primary" icon={Lock} className="w-full mt-5"
                loading={busy} disabled={!password || !confirm} onClick={save}>
                Set new password
              </Button>
            </>
          )}

          {step === 'done' && (
            <div className="text-center py-4">
              <CheckCircle2 size={34} className="mx-auto text-emerald-600 mb-3" />
              <h1 className="text-lg font-semibold text-slate-900">Password changed</h1>
              <p className="text-sm text-slate-500 mt-1 mb-6">
                Sign in with your new password.
              </p>
              <Button variant="primary" className="w-full"
                onClick={() => navigate('/login')}>Go to sign in</Button>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
