import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Search, MapPin, Crosshair, Phone, Send, CheckCircle2, ArrowLeft, SlidersHorizontal,
  Navigation, MessageCircle, ChevronDown, BedDouble, Inbox, LogOut, Loader2,
  Map as MapIcon, List as ListIcon, ImageOff,
} from 'lucide-react'
import { publicApi } from '@/services/api/publicApi'
import { useApi } from '@/lib/useApi'
import { currentPosition, formatDistance, LocationError } from '@/lib/geo'
import { readSeekerToken, writeSeekerToken } from '@/lib/seekerSession'
import { relative } from '@/lib/format'
import {
  Card, Button, FormField, Input, Select, Textarea, Modal, InlineAlert, EmptyState,
  Skeleton, StatusBadge, PgMap, PlaceChooser,
} from '@/components/ui'
import { useToast } from '@/context/ToastContext'

/**
 * Finding a PG. Public: browsing needs no account.
 *
 * Opens on "near me" - the phone's position is asked for straight away,
 * because that is the question everyone arriving here has. But that only serves
 * someone standing where they want to live. Looking for a friend, or near a
 * campus, or beside a job that starts next month, needs a point you are not
 * standing on - so there is a real map (Leaflet over OpenStreetMap) where a pin
 * can be dropped anywhere, plus area search by name, which the API geocodes.
 * All three routes end in the same latitude, longitude and label.
 *
 * Enquiring needs a seeker account: name, phone, and an email proved with a
 * code, once. After that every enquiry is one tap, and "My enquiries" shows
 * what each PG did with it. The account is deliberately separate from staff and
 * resident logins - see backend app/models/seeker.py.
 *
 * Availability comes from the API as bands ("a few beds"), per kind of room.
 * This screen must never try to turn those back into a number.
 */

const RADII = [2, 5, 10, 25]
const ENQUIRY_STATUS = {
  NEW: ['Sent', 'blue'],
  CONTACTED: ['PG contacted you', 'amber'],
  VISITED: ['Visited', 'violet'],
  CONVERTED: ['Moved in', 'emerald'],
  CLOSED: ['Closed', 'slate'],
}
const PHONE = /^[\d\s+\-()]{8,}$/
const EMAIL = /^\S+@\S+\.\S+$/

const rupees = (n) => `₹${Number(n).toLocaleString('en-IN')}`
const titleOf = (pg) => pg.pg_name || pg.name
const lowestRent = (pg) => pg.starting_rent ?? (pg.room_options || []).reduce(
  (low, o) => (o.from_rent != null && (low == null || o.from_rent < low) ? o.from_rent : low), null)
const waDigits = (phone) => {
  const d = String(phone || '').replace(/\D/g, '')
  return d.length === 10 ? `91${d}` : d
}
const whatsappUrl = (pg) => `https://wa.me/${waDigits(pg.contact_phone)}?text=${
  encodeURIComponent(`Hi, I found ${titleOf(pg)} on PGuru. Is a bed available?`)}`
const mapsUrl = (pg) => (pg.latitude != null && pg.longitude != null
  ? `https://www.google.com/maps/dir/?api=1&destination=${pg.latitude},${pg.longitude}`
  : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
    [pg.name, pg.address, pg.city].filter(Boolean).join(', '))}`)
const genderLabel = (g) => (g === 'MALE' ? 'Men only' : g === 'FEMALE' ? 'Women only' : 'Anyone')
const initials = (name) => (name || '?').trim().split(/\s+/).slice(0, 2)
  .map((w) => w[0]).join('').toUpperCase()

export default function FindPG() {
  const routerLocation = useLocation()
  const { success } = useToast()

  const [seeker, setSeeker] = useState(null)
  const [auth, setAuth] = useState(null)              // { mode, then }
  const [accountOpen, setAccountOpen] = useState(false)
  const [view, setView] = useState('search')          // search | mine
  const [layout, setLayout] = useState('list')        // list | map

  const [place, setPlace] = useState(null)            // { latitude, longitude, label }
  const [booted, setBooted] = useState(false)
  const [locating, setLocating] = useState(false)
  const [locError, setLocError] = useState(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [radius, setRadius] = useState(5)

  const [text, setText] = useState('')
  const [filters, setFilters] = useState({ max_rent: '', gender: '', only_vacant: true })
  const [applied, setApplied] = useState({ q: '', max_rent: '', gender: '', only_vacant: true })
  const [showFilters, setShowFilters] = useState(false)

  const [detail, setDetail] = useState(null)
  const [enquiring, setEnquiring] = useState(null)

  /* ------------------------------------------------------ seeker session */
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!(await readSeekerToken())) return
      try {
        const me = await publicApi.seekerMe()
        if (!cancelled) setSeeker(me)
      } catch (err) {
        if (err?.status === 401) await writeSeekerToken(null)
      }
    })()
    return () => { cancelled = true }
  }, [])

  // Arriving from signup's "I am looking for a PG".
  useEffect(() => {
    if (routerLocation.state?.openAuth) setAuth({ mode: routerLocation.state.openAuth })
  }, [routerLocation.state])

  /* ------------------------------------------------------------ location */
  const nameThePlace = useCallback(async (latitude, longitude) => {
    try {
      const found = await publicApi.reversePlace(latitude, longitude)
      if (found?.label) {
        setPlace((p) => (p && p.latitude === latitude && p.longitude === longitude
          ? { ...p, label: found.label } : p))
      }
    } catch { /* coordinates work fine without a name */ }
  }, [])

  const detect = useCallback(async () => {
    setLocating(true)
    try {
      const pos = await currentPosition({ highAccuracy: false, maximumAge: 5 * 60 * 1000, timeout: 12000 })
      setPlace({ latitude: pos.latitude, longitude: pos.longitude, label: 'your location' })
      setLocError(null)
      nameThePlace(pos.latitude, pos.longitude)
    } catch (err) {
      setLocError(err instanceof LocationError ? err.message : 'Could not read your location.')
    } finally {
      setLocating(false)
      setBooted(true)
    }
  }, [nameThePlace])

  useEffect(() => { detect() }, [detect])

  /* ------------------------------------------------------------- results */
  const results = useApi(() => publicApi.searchPgs({
    q: applied.q || undefined,
    max_rent: applied.max_rent || undefined,
    gender: applied.gender || undefined,
    only_vacant: applied.only_vacant,
    latitude: place?.latitude,
    longitude: place?.longitude,
    radius_km: place ? radius : undefined,
    limit: 40,
  }), [JSON.stringify(applied), place?.latitude, place?.longitude, radius], { enabled: booted })

  const rows = results.data || []
  // Only PGs whose owner actually set a position can be drawn. The rest still
  // appear in the list, and the count above says how many are missing rather
  // than letting the map quietly look emptier than the search really was.
  const mappable = rows.filter((r) => r.latitude != null && r.longitude != null)
    .map((r) => ({ id: r.id, latitude: r.latitude, longitude: r.longitude, name: titleOf(r) }))
  const wider = RADII.find((r) => r > radius)
  const runSearch = () => setApplied({ ...filters, q: text.trim() })

  const enquire = (pg) => {
    if (seeker) setEnquiring(pg)
    else setAuth({ mode: 'signup', then: pg })
  }
  const onAuthed = (profile, then) => {
    setSeeker(profile)
    setAuth(null)
    success(`Signed in as ${profile.full_name}`)
    if (then) setEnquiring(then)
  }
  const sessionLost = useCallback(async () => {
    await writeSeekerToken(null)
    setSeeker(null)
    setView('search')
  }, [])
  const signOut = async () => {
    try { await publicApi.seekerLogout() } catch { /* already gone */ }
    setAccountOpen(false)
    await sessionLost()
  }

  return (
    <div className="min-h-dvh bg-canvas">
      <header className="bg-white border-b border-line sticky top-0 z-20 safe-t">
        <div className="max-w-5xl mx-auto px-4 pt-3 pb-3 space-y-2.5">
          <div className="flex items-center gap-2">
            <Link to="/login" aria-label="Back to sign in"
              className="h-9 w-9 -ml-2 inline-flex items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 shrink-0">
              <ArrowLeft size={18} />
            </Link>
            <img src="/pgguru-logo.png" alt="PGuru" className="h-10 w-auto flex-1 min-w-0 object-contain object-left" />
            <h1 className="sr-only">Find a PG</h1>
            {seeker ? (
              <button type="button" onClick={() => setAccountOpen(true)}
                className="flex items-center gap-2 rounded-full pl-1 pr-3 py-1 hover:bg-slate-100">
                <span className="h-7 w-7 rounded-full bg-brand-700 text-white text-xs font-semibold inline-flex items-center justify-center">
                  {initials(seeker.full_name)}
                </span>
                <span className="text-sm text-slate-700 max-w-[8rem] truncate">
                  {seeker.full_name.split(' ')[0]}
                </span>
              </button>
            ) : (
              <Button size="sm" onClick={() => setAuth({ mode: 'signin' })}>Sign in</Button>
            )}
          </div>

          {seeker && (
            <div className="grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1" role="tablist">
              {[['search', 'Search'], ['mine', 'My enquiries']].map(([key, label]) => (
                <button key={key} type="button" role="tab" aria-selected={view === key}
                  onClick={() => setView(key)}
                  className={`h-8 rounded-md text-sm transition-colors ${view === key
                    ? 'bg-white text-slate-900 font-medium shadow-card' : 'text-slate-500'}`}>
                  {label}
                </button>
              ))}
            </div>
          )}

          {view === 'search' && (
            <>
              <button type="button" onClick={() => setPickerOpen(true)}
                className="w-full flex items-center gap-2 rounded-lg border border-line px-3 h-10 text-left hover:border-slate-300">
                {locating
                  ? <Loader2 size={16} className="text-brand-600 animate-spin shrink-0" />
                  : <MapPin size={16} className="text-brand-600 shrink-0" />}
                <span className="text-sm text-slate-900 truncate flex-1">
                  {locating && !place ? 'Finding where you are…'
                    : place ? `Near ${place.label}` : 'Choose an area'}
                </span>
                <ChevronDown size={16} className="text-slate-400 shrink-0" />
              </button>

              <div className="flex gap-2">
                <div className="relative flex-1 min-w-0">
                  <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                  <Input value={text} placeholder="PG name, landmark or street" className="pl-9"
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && runSearch()} />
                </div>
                <Button variant="primary" icon={Search} onClick={runSearch} aria-label="Search">
                  <span className="hidden sm:inline">Search</span>
                </Button>
              </div>

              <div className="flex items-center gap-1.5 overflow-x-auto -mx-4 px-4 pb-0.5">
                {place && RADII.map((km) => (
                  <button key={km} type="button" onClick={() => setRadius(km)}
                    className={`h-8 px-3 rounded-full text-xs whitespace-nowrap border transition-colors ${radius === km
                      ? 'bg-brand-700 border-brand-700 text-white font-medium'
                      : 'bg-white border-line text-slate-600'}`}>
                    {km} km
                  </button>
                ))}
                <button type="button" onClick={() => setShowFilters((v) => !v)}
                  className={`h-8 px-3 rounded-full text-xs whitespace-nowrap border inline-flex items-center gap-1.5 ${showFilters
                    ? 'border-brand-400 text-brand-800 bg-brand-50' : 'bg-white border-line text-slate-600'}`}>
                  <SlidersHorizontal size={13} /> Filters
                </button>
                <button type="button" onClick={() => setLayout(layout === 'map' ? 'list' : 'map')}
                  aria-pressed={layout === 'map'}
                  className={`h-8 px-3 rounded-full text-xs whitespace-nowrap border inline-flex items-center gap-1.5 ml-auto ${layout === 'map'
                    ? 'border-brand-400 text-brand-800 bg-brand-50' : 'bg-white border-line text-slate-600'}`}>
                  {layout === 'map'
                    ? <><ListIcon size={13} /> List</>
                    : <><MapIcon size={13} /> Map</>}
                </button>
              </div>

              {showFilters && (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-1">
                  <FormField label="Max rent">
                    <Input type="number" inputMode="numeric" value={filters.max_rent} placeholder="12000"
                      className="tnum" onChange={(e) => setFilters((f) => ({ ...f, max_rent: e.target.value }))} />
                  </FormField>
                  <FormField label="For">
                    <Select value={filters.gender}
                      onChange={(e) => setFilters((f) => ({ ...f, gender: e.target.value }))}>
                      <option value="">Anyone</option>
                      <option value="MALE">Men</option>
                      <option value="FEMALE">Women</option>
                    </Select>
                  </FormField>
                  <label className="col-span-2 sm:col-span-1 flex items-center gap-2 text-sm text-slate-700 sm:mt-6">
                    <input type="checkbox" checked={filters.only_vacant}
                      onChange={(e) => setFilters((f) => ({ ...f, only_vacant: e.target.checked }))} />
                    Only PGs with a free bed
                  </label>
                  <div className="col-span-2 sm:col-span-3">
                    <Button variant="primary" size="sm"
                      onClick={() => { runSearch(); setShowFilters(false) }}>Apply filters</Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-4">
        {view === 'mine' && seeker ? (
          <MyEnquiries seeker={seeker} onSessionLost={sessionLost} />
        ) : (
          <>
            {locError && !place && (
              <InlineAlert tone="info" className="mb-4" title="See PGs near you">
                {locError} You can also pick an area to search around.
                <div className="mt-2.5 flex flex-wrap gap-2">
                  <Button size="sm" icon={Crosshair} loading={locating} onClick={detect}>Try again</Button>
                  <Button size="sm" icon={MapPin} onClick={() => setPickerOpen(true)}>Pick an area</Button>
                </div>
              </InlineAlert>
            )}

            {results.error ? (
              <InlineAlert tone="error">{results.error.message}</InlineAlert>
            ) : !booted || (results.loading && !results.data) ? (
              <div className="grid sm:grid-cols-2 gap-3">
                {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-52" />)}
              </div>
            ) : rows.length === 0 ? (
              <EmptyState icon={BedDouble}
                title={applied.only_vacant ? 'No free beds found here' : 'No PGs found'}
                message={place ? `Nothing listed within ${radius} km of ${place.label}.`
                  : 'Try another area, or clear the filters. Only PGs that chose to be listed appear here.'}
                action={place && wider
                  ? <Button onClick={() => setRadius(wider)}>Search within {wider} km</Button> : null} />
            ) : (
              <>
                <p className="text-xs text-slate-500 mb-3 tnum">
                  {rows.length} PG{rows.length === 1 ? '' : 's'}
                  {place ? ` within ${radius} km, closest first` : ', cheapest first'}
                  {layout === 'map' && mappable.length < rows.length
                    ? ` · ${rows.length - mappable.length} not on the map yet` : ''}
                </p>

                {layout === 'map' ? (
                  <div className="space-y-3">
                    <PgMap value={place} radiusKm={place ? radius : null} height={380}
                      results={mappable}
                      onPick={(point) => setPlace({ ...point, label: 'the pin you dropped' })}
                      onOpenResult={(id) => {
                        const found = rows.find((r) => r.id === id)
                        if (found) setDetail(found)
                      }} />
                    <p className="text-xs text-slate-500">
                      Tap a green dot to open that PG. Drag the blue pin to search
                      somewhere else.
                    </p>
                  </div>
                ) : (
                  <div className="grid sm:grid-cols-2 gap-3">
                    {rows.map((pg) => (
                      <PgCard key={pg.id} pg={pg} onOpen={() => setDetail(pg)} onEnquire={() => enquire(pg)} />
                    ))}
                  </div>
                )}
              </>
            )}

            <Link to="/signup"
              className="mt-8 block rounded-xl border border-dashed border-slate-300 bg-white px-4 py-3.5 text-sm text-slate-600 hover:border-brand-300">
              <span className="font-medium text-slate-900">Run a PG?</span> List your free beds
              here for free and get enquiries straight to your phone.
            </Link>
          </>
        )}
      </main>

      <LocationPicker open={pickerOpen} onClose={() => setPickerOpen(false)}
        value={place} locating={locating}
        onPick={(p) => { setPlace(p); setLocError(null); setPickerOpen(false) }}
        onUseGps={() => { setPickerOpen(false); detect() }} />
      <PgDetail pg={detail} onClose={() => setDetail(null)}
        onEnquire={(pg) => { setDetail(null); enquire(pg) }} />
      <SeekerAuth state={auth} onClose={() => setAuth(null)} onDone={onAuthed} />
      <EnquiryDialog pg={enquiring} seeker={seeker} onClose={() => setEnquiring(null)}
        onSessionLost={() => {
          const pg = enquiring
          setEnquiring(null)
          sessionLost()
          setAuth({ mode: 'signin', then: pg })
        }} />
      <AccountSheet open={accountOpen} seeker={seeker} onClose={() => setAccountOpen(false)}
        onSignOut={signOut} onSaved={setSeeker} />
    </div>
  )
}

/* --------------------------------------------------------------- card */
function PgCard({ pg, onOpen, onEnquire }) {
  const rent = lowestRent(pg)
  // The search sends the lead photo only - forty results carrying six 5 KB
  // photos each would be over a megabyte of base64 on mobile data.
  const lead = pg.photos?.[0]
  return (
    <Card className="overflow-hidden flex flex-col">
      <button type="button" onClick={onOpen} className="block w-full text-left">
        {lead ? (
          <img src={lead.data_url} alt={lead.caption || titleOf(pg)}
            className="w-full h-32 object-cover bg-slate-100" />
        ) : (
          <div className="w-full h-32 bg-slate-50 flex flex-col items-center justify-center gap-1 text-slate-300">
            <ImageOff size={20} />
            <span className="text-2xs text-slate-400">No photo yet</span>
          </div>
        )}
      </button>
      <div className="p-4 flex flex-col flex-1">
      <button type="button" onClick={onOpen} className="text-left">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-900 truncate">{titleOf(pg)}</p>
            {pg.pg_name && pg.pg_name !== pg.name && (
              <p className="text-xs text-slate-500 truncate">{pg.name}</p>
            )}
          </div>
          <StatusBadge status={pg.has_vacancy ? pg.vacancy : 'Full'}
            tone={pg.has_vacancy ? 'emerald' : 'slate'} />
        </div>

        <p className="text-xs text-slate-500 mt-1.5 flex items-center gap-1">
          <MapPin size={11} className="shrink-0" />
          <span className="truncate">{pg.address || pg.city || '—'}</span>
          {pg.distance_m != null && (
            <span className="tnum shrink-0 font-medium text-slate-700">· {formatDistance(pg.distance_m)}</span>
          )}
        </p>

        {pg.room_options?.length > 0 && (
          <ul className="mt-3 space-y-1">
            {pg.room_options.slice(0, 3).map((o) => (
              <li key={o.room_type} className="flex items-center justify-between gap-2 text-xs">
                <span className="flex items-center gap-1.5 text-slate-700 min-w-0">
                  <BedDouble size={12} className="text-slate-400 shrink-0" />
                  <span className="truncate">{o.room_type}</span>
                </span>
                <span className="shrink-0 text-slate-500 tnum">
                  {o.from_rent != null ? `${rupees(o.from_rent)} · ` : ''}{o.vacancy}
                </span>
              </li>
            ))}
          </ul>
        )}
      </button>

      <div className="flex items-end justify-between gap-2 mt-auto pt-4">
        <div className="min-w-0">
          {rent != null ? (
            <p className="text-sm font-semibold text-slate-900 tnum">
              {rupees(rent)}<span className="text-2xs font-normal text-slate-500 ml-1">/month from</span>
            </p>
          ) : <p className="text-xs text-slate-500">Price on request</p>}
          <p className="text-2xs text-slate-500 mt-0.5">{genderLabel(pg.gender_preference)}</p>
        </div>
        <div className="flex gap-1.5 shrink-0">
          {pg.contact_phone && (
            <a href={`tel:${pg.contact_phone}`} aria-label={`Call ${titleOf(pg)}`}
              className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-line text-slate-600 hover:bg-slate-50">
              <Phone size={14} />
            </a>
          )}
          {pg.contact_phone && (
            <a href={whatsappUrl(pg)} target="_blank" rel="noreferrer" aria-label="WhatsApp"
              className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-line text-emerald-600 hover:bg-emerald-50">
              <MessageCircle size={14} />
            </a>
          )}
          <Button size="sm" variant="primary" icon={Send} onClick={onEnquire}>Enquire</Button>
        </div>
      </div>
      </div>
    </Card>
  )
}

/* ------------------------------------------------------------- detail */
function PgDetail({ pg: summary, onClose, onEnquire }) {
  /**
   * Opening a PG fetches it again, for one reason: photos.
   *
   * The search deliberately sends only the lead photo per result, so the whole
   * gallery does not exist in the row that was tapped. Everything else is
   * already correct in the summary, so the fetched copy is merged over it and
   * the sheet renders immediately either way - no spinner over content the
   * person can already see.
   */
  const [full, setFull] = useState(null)

  useEffect(() => {
    setFull(null)
    if (!summary?.id) return undefined
    let cancelled = false
    ;(async () => {
      try {
        const found = await publicApi.getPg(summary.id)
        if (!cancelled && found) setFull(found)
      } catch { /* the summary is enough to show the sheet */ }
    })()
    return () => { cancelled = true }
  }, [summary?.id])

  if (!summary) return null
  const pg = full ? { ...summary, ...full, distance_m: summary.distance_m } : summary
  return (
    <Modal open={!!pg} onClose={onClose} size="md" title={titleOf(pg)}
      subtitle={[pg.pg_name && pg.pg_name !== pg.name ? pg.name : null, pg.city]
        .filter(Boolean).join(' · ') || undefined}
      footer={<>
        {pg.contact_phone && (
          <a href={`tel:${pg.contact_phone}`}><Button icon={Phone} className="w-full sm:w-auto">Call</Button></a>
        )}
        <a href={mapsUrl(pg)} target="_blank" rel="noreferrer">
          <Button icon={Navigation} className="w-full sm:w-auto">Directions</Button>
        </a>
        <Button variant="primary" icon={Send} onClick={() => onEnquire(pg)}>Enquire</Button>
      </>}>
      <div className="space-y-5">
        {pg.photos?.length > 0 && (
          <div className="-mx-4 sm:-mx-5 px-4 sm:px-5 flex gap-2 overflow-x-auto pb-1">
            {pg.photos.map((photo) => (
              <figure key={photo.id} className="shrink-0 w-44">
                <img src={photo.data_url} alt={photo.caption || titleOf(pg)}
                  className="w-44 h-32 object-cover rounded-lg bg-slate-100" />
                {photo.caption && (
                  <figcaption className="text-2xs text-slate-500 mt-1 truncate">
                    {photo.caption}
                  </figcaption>
                )}
              </figure>
            ))}
          </div>
        )}
        {pg.headline && <p className="text-sm font-medium text-slate-800">{pg.headline}</p>}
        {pg.description && <p className="text-sm text-slate-600 whitespace-pre-line">{pg.description}</p>}

        <div>
          <p className="text-[13px] font-semibold text-slate-800 mb-2">Rooms with a free bed</p>
          {pg.room_options?.length ? (
            <div className="divide-y divide-line rounded-lg border border-line">
              {pg.room_options.map((o) => (
                <div key={o.room_type} className="px-3 py-2.5 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm text-slate-900">{o.room_type}</p>
                    {o.sharing ? (
                      <p className="text-2xs text-slate-500">
                        {o.sharing === 1 ? 'Private room' : `${o.sharing} sharing`}
                      </p>
                    ) : null}
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-medium text-slate-900 tnum">
                      {o.from_rent != null ? `${rupees(o.from_rent)}/mo` : 'On request'}
                    </p>
                    <p className="text-2xs text-emerald-700">{o.vacancy}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">
              No free beds right now. Enquire and the PG can tell you when one opens up.
            </p>
          )}
        </div>

        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div><dt className="text-xs text-slate-500">For</dt>
            <dd className="text-slate-800">{genderLabel(pg.gender_preference)}</dd></div>
          <div><dt className="text-xs text-slate-500">Distance</dt>
            <dd className="text-slate-800 tnum">{pg.distance_m != null ? formatDistance(pg.distance_m) : '—'}</dd></div>
          <div className="col-span-2"><dt className="text-xs text-slate-500">Address</dt>
            <dd className="text-slate-800">{[pg.address, pg.city].filter(Boolean).join(', ') || '—'}</dd></div>
        </dl>

        {pg.amenities?.length > 0 && (
          <div>
            <p className="text-[13px] font-semibold text-slate-800 mb-2">Amenities</p>
            <div className="flex flex-wrap gap-1.5">
              {pg.amenities.map((a) => (
                <span key={a} className="text-xs rounded-full bg-slate-100 text-slate-700 px-2.5 py-1">{a}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}

/* ------------------------------------------------------ area picker */
/**
 * Where to search.
 *
 * Was a text box and a list of names. That works for "PGs in Koramangala" and
 * fails for everything else - most of all for the person looking on behalf of
 * someone who is moving to a city they have never been to. A map they can point
 * at answers that; a list of place names does not.
 *
 * The three routes in (GPS, typing, dropping a pin) all live in PlaceChooser
 * and all produce the same { latitude, longitude, label }, so nothing
 * downstream has to know which one was used.
 */
function LocationPicker({ open, onClose, onPick, onUseGps, value, locating }) {
  const [draft, setDraft] = useState(value || null)

  useEffect(() => { if (open) setDraft(value || null) }, [open, value])

  return (
    <Modal open={open} onClose={onClose} size="md" title="Search near"
      subtitle="Use your location, type an area, or drop a pin anywhere."
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={!draft} icon={Search}
          onClick={() => draft && onPick(draft)}>
          Search here
        </Button>
      </>}>
      <PlaceChooser value={draft} onChange={setDraft} onUseGps={onUseGps}
        locating={locating} height={300} />
    </Modal>
  )
}

/* --------------------------------------------------- seeker sign-in */
function SeekerAuth({ state, onClose, onDone }) {
  const [mode, setMode] = useState('signup')
  const [stage, setStage] = useState('form')          // form | code | profile
  const [form, setForm] = useState({ full_name: '', phone: '', email: '' })
  const [code, setCode] = useState('')
  const [token, setToken] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!state) return
    setMode(state.mode === 'signin' ? 'signin' : 'signup')
    setStage('form'); setCode(''); setToken(null); setError(null)
  }, [state])

  if (!state) return null
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const email = form.email.trim().toLowerCase()

  const profileProblem = () => {
    if (form.full_name.trim().length < 2) return 'Enter your name.'
    if (!PHONE.test(form.phone)) return 'Enter a phone number PGs can call you on.'
    return null
  }

  const sendCode = async () => {
    const problem = mode === 'signup' ? profileProblem() : null
    if (problem) return setError(problem)
    if (!EMAIL.test(email)) return setError('Enter a valid email address.')
    setBusy(true); setError(null)
    try {
      await publicApi.sendCode(email)
      setStage('code')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const finish = async (verification_token, withProfile) => {
    const body = { verification_token }
    if (withProfile) {
      body.full_name = form.full_name.trim()
      body.phone = form.phone.trim() || null
    }
    const res = await publicApi.seekerSession(body)
    await writeSeekerToken(res.token)
    onDone(res.seeker, state.then)
  }

  const verify = async () => {
    setBusy(true); setError(null)
    try {
      const res = await publicApi.verifyCode(email, code.trim())
      setToken(res.verification_token)
      try {
        await finish(res.verification_token, mode === 'signup')
      } catch (err) {
        // No account for this email yet: ask for a name, keep the same token.
        if (err.code === 'needs_profile') { setStage('profile'); return }
        throw err
      }
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const completeProfile = async () => {
    const problem = profileProblem()
    if (problem) return setError(problem)
    setBusy(true); setError(null)
    try { await finish(token, true) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const title = stage === 'code' ? 'Check your email'
    : stage === 'profile' ? 'Almost done'
      : mode === 'signup' ? 'Create your free account' : 'Sign in'

  const nameAndPhone = (
    <>
      <FormField label="Your name" required>
        <Input value={form.full_name} onChange={set('full_name')} autoComplete="name" />
      </FormField>
      <FormField label="Phone" required hint="PGs use this to call you back.">
        <Input value={form.phone} onChange={set('phone')} inputMode="tel" autoComplete="tel"
          placeholder="+91 98765 43210" />
      </FormField>
    </>
  )

  return (
    <Modal open={!!state} onClose={onClose} size="sm" title={title}
      subtitle={stage === 'form' ? (mode === 'signup'
        ? 'Enquire at any PG in one tap. PGs call you back directly.'
        : 'We will email you a 6-digit code. No password needed.') : undefined}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        {stage === 'form' && <Button variant="primary" loading={busy} onClick={sendCode}>Send code</Button>}
        {stage === 'code' && (
          <Button variant="primary" loading={busy} disabled={code.length < 6} onClick={verify}>Verify</Button>
        )}
        {stage === 'profile' && (
          <Button variant="primary" loading={busy} onClick={completeProfile}>Create account</Button>
        )}
      </>}>
      {error && <InlineAlert tone="error" className="mb-4">{error}</InlineAlert>}

      {stage === 'form' && (
        <div className="space-y-4">
          {mode === 'signup' && nameAndPhone}
          <FormField label="Email" required>
            <Input type="email" value={form.email} onChange={set('email')} autoComplete="email"
              onKeyDown={(e) => e.key === 'Enter' && sendCode()} />
          </FormField>
          <p className="text-xs text-slate-500 text-center">
            {mode === 'signup' ? 'Already have an account? ' : 'New here? '}
            <button type="button" className="text-brand-700 font-medium"
              onClick={() => { setMode(mode === 'signup' ? 'signin' : 'signup'); setError(null) }}>
              {mode === 'signup' ? 'Sign in' : 'Create an account'}
            </button>
          </p>
        </div>
      )}

      {stage === 'code' && (
        <FormField label="6-digit code"
          hint={`Sent to ${email}. It expires in 10 minutes. Check spam if it has not arrived.`}>
          <Input value={code} autoFocus inputMode="numeric" maxLength={6} autoComplete="one-time-code"
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            onKeyDown={(e) => e.key === 'Enter' && code.length === 6 && verify()}
            className="tnum text-center text-xl tracking-[0.5em]" placeholder="000000" />
        </FormField>
      )}

      {stage === 'profile' && (
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            There is no account for {email} yet. Add your name and phone to create one.
          </p>
          {nameAndPhone}
        </div>
      )}
    </Modal>
  )
}

/* ----------------------------------------------------------- enquiry */
function EnquiryDialog({ pg, seeker, onClose, onSessionLost }) {
  const { success } = useToast()
  const [message, setMessage] = useState('')
  const [moveIn, setMoveIn] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sent, setSent] = useState(false)

  useEffect(() => {
    if (!pg) return
    const room = pg.room_options?.[0]?.room_type
    setMessage(room ? `Hi, is a bed available in ${room.toLowerCase()}?` : 'Hi, is a bed available?')
    setMoveIn(''); setError(null); setSent(false)
  }, [pg])

  if (!pg) return null

  const send = async () => {
    setBusy(true); setError(null)
    try {
      await publicApi.seekerEnquire({
        branch_id: pg.id, message: message.trim() || null, move_in_date: moveIn || null,
      })
      setSent(true)
      success('Enquiry sent', `${titleOf(pg)} will contact you directly.`)
    } catch (err) {
      if (err.status === 401) { onSessionLost?.(); return }
      setError(err.message)
    } finally { setBusy(false) }
  }

  return (
    <Modal open={!!pg} onClose={onClose} size="sm"
      title={sent ? 'Enquiry sent' : `Enquire at ${titleOf(pg)}`}
      footer={sent
        ? <Button variant="primary" onClick={onClose}>Done</Button>
        : <><Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" icon={Send} loading={busy} onClick={send}>Send enquiry</Button></>}>
      {sent ? (
        <div className="text-center py-4">
          <CheckCircle2 size={32} className="mx-auto text-emerald-600 mb-3" />
          <p className="text-sm text-slate-700">
            {titleOf(pg)} has your details and will call you
            {seeker?.phone ? ` on ${seeker.phone}` : ''}. Follow it under My enquiries.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {error && <InlineAlert tone="error">{error}</InlineAlert>}
          <p className="text-xs text-slate-500">
            Sending as {seeker?.full_name}{seeker?.phone ? ` · ${seeker.phone}` : ''}
          </p>
          <FormField label="Message">
            <Textarea rows={3} value={message} maxLength={1000}
              onChange={(e) => setMessage(e.target.value)} />
          </FormField>
          <FormField label="When do you want to move in?" hint="Optional">
            <Input type="date" value={moveIn} onChange={(e) => setMoveIn(e.target.value)} />
          </FormField>
        </div>
      )}
    </Modal>
  )
}

/* ------------------------------------------------------ my enquiries */
function MyEnquiries({ seeker, onSessionLost }) {
  const list = useApi(() => publicApi.seekerEnquiries(), [seeker?.id])

  useEffect(() => {
    if (list.error?.status === 401) onSessionLost?.()
  }, [list.error, onSessionLost])

  if (list.loading && !list.data) {
    return <div className="space-y-2.5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />)}</div>
  }
  if (list.error) return <InlineAlert tone="error">{list.error.message}</InlineAlert>

  const rows = list.data || []
  if (!rows.length) {
    return (
      <EmptyState icon={Inbox} title="No enquiries yet"
        message="Find a PG you like and tap Enquire. It shows up here with the PG's progress." />
    )
  }
  return (
    <div className="space-y-2.5">
      {rows.map((e) => {
        const [label, tone] = ENQUIRY_STATUS[e.status] || [e.status, 'slate']
        return (
          <Card key={e.id} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-900 truncate">{e.pg_name}</p>
                <p className="text-xs text-slate-500 truncate">
                  {[e.branch_name, e.city].filter(Boolean).join(' · ')}
                </p>
              </div>
              <StatusBadge status={label} tone={tone} dot />
            </div>
            {e.message && <p className="text-sm text-slate-600 mt-2 line-clamp-2">{e.message}</p>}
            <div className="flex items-center justify-between gap-2 mt-3">
              <p className="text-2xs text-slate-400">Sent {relative(e.created_at)}</p>
              {e.contact_phone && (
                <a href={`tel:${e.contact_phone}`}><Button size="sm" icon={Phone}>Call</Button></a>
              )}
            </div>
          </Card>
        )
      })}
    </div>
  )
}

/* ---------------------------------------------------------- account */
function AccountSheet({ open, seeker, onClose, onSignOut, onSaved }) {
  const { success, error } = useToast()
  const [f, setF] = useState({ full_name: '', phone: '' })
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open && seeker) setF({ full_name: seeker.full_name || '', phone: seeker.phone || '' })
  }, [open, seeker])

  if (!seeker) return null
  const save = async () => {
    setBusy(true)
    try {
      const me = await publicApi.seekerUpdate({ full_name: f.full_name.trim(), phone: f.phone.trim() })
      onSaved(me)
      success('Saved')
      onClose()
    } catch (err) {
      error('Could not save', err.message)
    } finally { setBusy(false) }
  }

  return (
    <Modal open={open} onClose={onClose} size="sm" title="Your account" subtitle={seeker.email}
      footer={<>
        <Button icon={LogOut} onClick={onSignOut}>Sign out</Button>
        <Button variant="primary" loading={busy} onClick={save}>Save</Button>
      </>}>
      <div className="space-y-4">
        <FormField label="Name">
          <Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />
        </FormField>
        <FormField label="Phone" hint="PGs call you on this number.">
          <Input value={f.phone} inputMode="tel" onChange={(e) => setF({ ...f, phone: e.target.value })} />
        </FormField>
      </div>
    </Modal>
  )
}
