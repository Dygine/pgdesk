import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Search, MapPin, Crosshair, IndianRupee, BedDouble, Phone, Send,
  CheckCircle2, ArrowLeft, SlidersHorizontal,
} from 'lucide-react'
import { publicApi } from '@/services/api/publicApi'
import { useApi } from '@/lib/useApi'
import { currentPosition, formatDistance, LocationError } from '@/lib/geo'
import {
  Card, Button, FormField, Input, Select, Modal, InlineAlert, EmptyState,
  Skeleton, StatusBadge,
} from '@/components/ui'
import { useToast } from '@/context/ToastContext'

/**
 * Finding a PG. Public, no login.
 *
 * Only PGs whose owner switched listing on appear here, and vacancy shows as a
 * band ("a few beds") rather than a count. That is the API's decision, not this
 * screen's, and this screen must not undo it by inferring a number from
 * anything else on the card.
 *
 * Sending an enquiry needs a verified email. Someone arriving from signup
 * already has a token and never sees the verification step; someone who landed
 * here directly verifies inside the enquiry dialog. Both end at the same place,
 * which is why the token lives in this component rather than in the dialog.
 */
export default function FindPG() {
  const location = useLocation()
  const passed = location.state || {}

  const [filters, setFilters] = useState({
    q: '', city: '', max_rent: '', gender: '', only_vacant: false,
  })
  const [applied, setApplied] = useState({})
  const [position, setPosition] = useState(null)
  const [locating, setLocating] = useState(false)
  const [locError, setLocError] = useState(null)
  const [showFilters, setShowFilters] = useState(false)
  const [enquiring, setEnquiring] = useState(null)

  // Verified identity carried over from signup, if they came that way.
  const [verified, setVerified] = useState({
    email: passed.verifiedEmail || null,
    token: passed.verificationToken || null,
  })

  const results = useApi(() => publicApi.searchPgs({
    ...applied,
    max_rent: applied.max_rent || undefined,
    latitude: position?.latitude,
    longitude: position?.longitude,
    radius_km: position ? 25 : undefined,
    limit: 40,
  }), [JSON.stringify(applied), position?.latitude, position?.longitude])

  const useMyLocation = useCallback(async () => {
    setLocating(true); setLocError(null)
    try {
      setPosition(await currentPosition())
    } catch (err) {
      setLocError(err instanceof LocationError ? err.message
        : 'Could not read your location.')
    } finally { setLocating(false) }
  }, [])

  const rows = results.data || []

  return (
    <div className="min-h-dvh bg-slate-50">
      <header className="bg-white border-b border-line sticky top-0 z-20">
        <div className="max-w-5xl mx-auto px-4 py-3">
          <div className="flex items-center gap-3">
            <Link to="/login" className="text-slate-500 hover:text-slate-800 shrink-0">
              <ArrowLeft size={18} />
            </Link>
            <div className="flex-1 min-w-0">
              <Input value={filters.q} placeholder="Search by area, name or landmark…"
                onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
                onKeyDown={(e) => e.key === 'Enter' && setApplied({ ...filters })} />
            </div>
            <Button icon={Search} variant="primary"
              onClick={() => setApplied({ ...filters })}>Search</Button>
          </div>

          <div className="flex items-center gap-2 mt-2 overflow-x-auto no-scrollbar">
            <Button size="sm" icon={Crosshair} loading={locating} onClick={useMyLocation}>
              {position ? 'Near me ✓' : 'Near me'}
            </Button>
            <Button size="sm" icon={SlidersHorizontal}
              onClick={() => setShowFilters((v) => !v)}>Filters</Button>
            {position && (
              <button type="button" onClick={() => setPosition(null)}
                className="text-xs text-slate-500 hover:text-slate-800 whitespace-nowrap px-2">
                Clear location
              </button>
            )}
          </div>

          {showFilters && (
            <div className="grid sm:grid-cols-3 gap-3 mt-3 pb-1">
              <FormField label="City">
                <Input value={filters.city}
                  onChange={(e) => setFilters((f) => ({ ...f, city: e.target.value }))} />
              </FormField>
              <FormField label="Max rent">
                <Input type="number" inputMode="numeric" value={filters.max_rent}
                  placeholder="12000" className="tnum"
                  onChange={(e) => setFilters((f) => ({ ...f, max_rent: e.target.value }))} />
              </FormField>
              <FormField label="For">
                <Select value={filters.gender}
                  onChange={(e) => setFilters((f) => ({ ...f, gender: e.target.value }))}>
                  <option value="">Anyone</option>
                  <option value="MALE">Men</option>
                  <option value="FEMALE">Women</option>
                </Select>
              </FormField>
              <label className="flex items-center gap-2 text-sm text-slate-700 sm:col-span-3">
                <input type="checkbox" checked={filters.only_vacant}
                  onChange={(e) => setFilters((f) => ({ ...f, only_vacant: e.target.checked }))} />
                Only show PGs with beds available
              </label>
              <div className="sm:col-span-3">
                <Button variant="primary" size="sm"
                  onClick={() => { setApplied({ ...filters }); setShowFilters(false) }}>
                  Apply filters
                </Button>
              </div>
            </div>
          )}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-5">
        {locError && <InlineAlert tone="warn" className="mb-4">{locError}</InlineAlert>}

        {results.error ? (
          <InlineAlert tone="error">{results.error.message}</InlineAlert>
        ) : results.loading && !results.data ? (
          <div className="grid sm:grid-cols-2 gap-3">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-44" />)}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState icon={Search} title="No PGs found"
            message={position
              ? 'Nothing listed within 25 km. Try clearing your location or widening the filters.'
              : 'Try a different area, or clear the filters. Only PGs that have chosen to be listed appear here.'} />
        ) : (
          <>
            <p className="text-xs text-slate-500 mb-3 tnum">
              {rows.length} PG{rows.length === 1 ? '' : 's'}
              {position ? ' near you, closest first' : ', cheapest first'}
            </p>
            <div className="grid sm:grid-cols-2 gap-3">
              {rows.map((pg) => (
                <PgCard key={pg.id} pg={pg} onEnquire={() => setEnquiring(pg)} />
              ))}
            </div>
          </>
        )}
      </main>

      <EnquiryDialog pg={enquiring} onClose={() => setEnquiring(null)}
        verified={verified} onVerified={setVerified} />
    </div>
  )
}

function PgCard({ pg, onEnquire }) {
  return (
    <Card className="p-4 flex flex-col">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-900 truncate">{pg.name}</p>
          {pg.headline && (
            <p className="text-xs text-slate-600 mt-0.5 line-clamp-2">{pg.headline}</p>
          )}
        </div>
        <StatusBadge status={pg.has_vacancy ? pg.vacancy : 'Full'}
          tone={pg.has_vacancy ? 'emerald' : 'slate'} />
      </div>

      <p className="text-xs text-slate-500 mt-2 flex items-center gap-1">
        <MapPin size={11} className="shrink-0" />
        <span className="truncate">{pg.address || pg.city || '—'}</span>
        {pg.distance_m != null && (
          <span className="tnum shrink-0"> · {formatDistance(pg.distance_m)}</span>
        )}
      </p>

      {pg.amenities?.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-3">
          {pg.amenities.slice(0, 4).map((a) => (
            <span key={a} className="text-2xs rounded-full bg-slate-100 text-slate-600 px-2 py-0.5">
              {a}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-end justify-between gap-2 mt-auto pt-4">
        <div>
          {pg.starting_rent != null ? (
            <p className="text-sm font-semibold text-slate-900 tnum flex items-center">
              <IndianRupee size={13} />{pg.starting_rent.toLocaleString('en-IN')}
              <span className="text-2xs font-normal text-slate-500 ml-1">/month from</span>
            </p>
          ) : (
            <p className="text-xs text-slate-500">Price on request</p>
          )}
          {pg.gender_preference && pg.gender_preference !== 'ANY' && (
            <p className="text-2xs text-slate-500 mt-0.5">
              {pg.gender_preference === 'MALE' ? 'Men only' : 'Women only'}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          {pg.contact_phone && (
            <a href={`tel:${pg.contact_phone}`}>
              <Button size="sm" icon={Phone} aria-label="Call" />
            </a>
          )}
          <Button size="sm" variant="primary" icon={Send} onClick={onEnquire}>
            Enquire
          </Button>
        </div>
      </div>
    </Card>
  )
}

/**
 * Enquiry, with verification folded in.
 *
 * Someone who arrived from signup already holds a token and goes straight to
 * the form. Someone who landed here from a link verifies first. Both paths end
 * in the same POST, which is why the token is owned by the page rather than
 * this dialog - verify once, enquire with as many PGs as you like.
 */
function EnquiryDialog({ pg, onClose, verified, onVerified }) {
  const { success } = useToast()
  const [email, setEmail] = useState(verified.email || '')
  const [code, setCode] = useState('')
  const [stage, setStage] = useState(verified.token ? 'form' : 'email')
  const [form, setForm] = useState({ full_name: '', phone: '', message: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sent, setSent] = useState(false)

  useEffect(() => {
    if (!pg) return
    setStage(verified.token ? 'form' : 'email')
    setSent(false); setError(null); setCode('')
  }, [pg, verified.token])

  if (!pg) return null

  const sendCode = async () => {
    setBusy(true); setError(null)
    try { await publicApi.sendCode(email.trim()); setStage('code') }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const checkCode = async () => {
    setBusy(true); setError(null)
    try {
      const res = await publicApi.verifyCode(email.trim(), code.trim())
      onVerified({ email: email.trim().toLowerCase(), token: res.verification_token })
      setStage('form')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const send = async () => {
    setBusy(true); setError(null)
    try {
      await publicApi.createEnquiry({
        branch_id: pg.id,
        verification_token: verified.token,
        full_name: form.full_name.trim(),
        phone: form.phone.trim() || null,
        message: form.message.trim() || null,
      })
      setSent(true)
      success('Enquiry sent', `${pg.name} will contact you directly.`)
      // The token is single use, so the next enquiry needs a fresh one. Say so
      // by clearing it rather than letting the following attempt fail.
      onVerified({ email: verified.email, token: null })
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <Modal open={!!pg} onClose={onClose} size="md" title={`Enquire — ${pg.name}`}
      footer={sent
        ? <Button variant="primary" onClick={onClose}>Done</Button>
        : <><Button onClick={onClose}>Cancel</Button>
            {stage === 'email' && (
              <Button variant="primary" loading={busy} disabled={!email.includes('@')}
                onClick={sendCode}>Send code</Button>)}
            {stage === 'code' && (
              <Button variant="primary" loading={busy} disabled={code.length < 4}
                onClick={checkCode}>Verify</Button>)}
            {stage === 'form' && (
              <Button variant="primary" icon={Send} loading={busy}
                disabled={!form.full_name.trim()} onClick={send}>Send enquiry</Button>)}
          </>}>

      {sent ? (
        <div className="text-center py-6">
          <CheckCircle2 size={32} className="mx-auto text-emerald-600 mb-3" />
          <p className="text-sm font-medium text-slate-900">Enquiry sent</p>
          <p className="text-xs text-slate-500 mt-1">
            {pg.name} has your details and will contact you directly. They will
            create your login once you move in.
          </p>
        </div>
      ) : (
        <>
          {error && <InlineAlert tone="error" className="mb-4">{error}</InlineAlert>}

          {stage === 'email' && (
            <>
              <p className="text-sm text-slate-600 mb-4">
                PGs get a lot of fake enquiries, so we confirm your email first.
                It takes a moment and you only do it once.
              </p>
              <FormField label="Your email">
                <Input type="email" value={email} autoFocus autoComplete="email"
                  onChange={(e) => setEmail(e.target.value)} />
              </FormField>
            </>
          )}

          {stage === 'code' && (
            <FormField label="6-digit code" hint={`Sent to ${email}. Expires in 10 minutes.`}>
              <Input value={code} autoFocus inputMode="numeric" maxLength={6}
                autoComplete="one-time-code"
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                className="tnum text-center text-xl tracking-[0.5em]" placeholder="000000" />
            </FormField>
          )}

          {stage === 'form' && (
            <div className="space-y-4">
              <p className="text-xs text-emerald-700 flex items-center gap-1.5">
                <CheckCircle2 size={13} /> {verified.email} verified
              </p>
              <FormField label="Your name" required>
                <Input value={form.full_name} autoFocus
                  onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} />
              </FormField>
              <FormField label="Phone" hint="How the PG will most likely reach you.">
                <Input value={form.phone} inputMode="tel"
                  onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} />
              </FormField>
              <FormField label="Message">
                <Input value={form.message} placeholder="Looking for a single room from next month"
                  onChange={(e) => setForm((f) => ({ ...f, message: e.target.value }))} />
              </FormField>
            </div>
          )}
        </>
      )}
    </Modal>
  )
}
