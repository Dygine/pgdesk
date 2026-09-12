import { useCallback, useEffect, useRef, useState } from 'react'
import {
  QrCode as QrIcon, LogIn, LogOut, RefreshCw, MapPin, ScanLine, CheckCircle2,
  Loader2, TriangleAlert,
} from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { meApi } from '@/services/api/meApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, StatusBadge, EmptyState, Skeleton, InlineAlert, Button,
  QrCode, ScannerModal, Tabs,
} from '@/components/ui'
import { dateTimeFmt } from '@/lib/format'
import { currentPosition, formatDistance, LocationError, requestPermission } from '@/lib/geo'

/**
 * The resident's gate screen.
 *
 * Two ways in, and both stay because neither covers everyone:
 *
 *   Check in myself  the resident scans the code posted at the gate, and the
 *                    phone's position is sent with it. Needs a smartphone, a
 *                    charged battery and GPS.
 *
 *   Show my code     the older direction, where a guard scans the resident.
 *                    Needs nothing but the card, which is why it cannot be
 *                    dropped: a dead phone is not a reason to have no
 *                    attendance record.
 *
 * The position is fetched on arrival rather than waiting for a button, because
 * a first GPS fix takes several seconds and asking for it after the tap makes
 * the scan feel broken. By the time anyone reaches the button the fix is in.
 */
export default function MyScan() {
  const { success, error: toastError } = useToast()
  const [tab, setTab] = useState('checkin')

  const { data, loading, error, reload } = useApi(() => meApi.qr(), [])

  /* ------------------------------------------------------------- position */
  const [position, setPosition] = useState(null)
  const [locating, setLocating] = useState(true)
  const [locError, setLocError] = useState(null)
  const mounted = useRef(true)

  useEffect(() => () => { mounted.current = false }, [])

  const locate = useCallback(async () => {
    setLocating(true)
    setLocError(null)
    try {
      await requestPermission()
      const fix = await currentPosition()
      if (mounted.current) setPosition(fix)
    } catch (err) {
      if (mounted.current) {
        setLocError(err instanceof LocationError ? err
          : new LocationError('failed', 'Could not read your location.'))
      }
    } finally {
      if (mounted.current) setLocating(false)
    }
  }, [])

  useEffect(() => { locate() }, [locate])

  /* --------------------------------------------------------- gate status */
  // Re-runs whenever a new fix arrives. The server decides whether this
  // position is close enough; the client never compares coordinates itself,
  // because a check that lives only in the app is a check an edited app skips.
  const gate = useApi(
    () => meApi.gateStatus(position ? {
      latitude: position.latitude,
      longitude: position.longitude,
      accuracy_m: position.accuracy ?? undefined,
    } : {}),
    [position?.latitude, position?.longitude, position?.accuracy])

  /* ---------------------------------------------------------------- scan */
  const [scanning, setScanning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  const submit = async (raw) => {
    setScanning(false)
    setBusy(true)
    setResult(null)
    try {
      // Read the position again at the moment of the scan rather than reusing
      // the one on screen. That fix could be minutes old - long enough to have
      // walked away - and the one recorded should be true when the code was read.
      let fix = position
      try {
        fix = await currentPosition({ timeout: 8000 })
        if (mounted.current) setPosition(fix)
      } catch { /* fall back to the displayed fix; the server still decides */ }

      const res = await meApi.selfScan({
        token: raw,
        latitude: fix?.latitude,
        longitude: fix?.longitude,
        accuracy_m: fix?.accuracy ?? undefined,
      })
      setResult(res)
      if (res.allowed) success(res.message)
      reload()
      gate.reload()
    } catch (err) {
      setResult({ allowed: false, message: err.message })
      toastError('Check-in refused', err.message)
    } finally {
      setBusy(false)
    }
  }

  if (error) {
    return (<><PageHeader title="My gate pass" />
      <InlineAlert tone="error" title="Could not load">{error.message}</InlineAlert></>)
  }
  if (loading && !data) {
    return (<><PageHeader title="My gate pass" /><Skeleton className="h-64" /></>)
  }

  const g = gate.data
  const enabled = g?.self_checkin_enabled
  const inRange = g?.in_range
  const nextIn = g?.next_direction !== 'EXIT'

  return (
    <>
      <PageHeader title="Gate"
        subtitle="Check yourself in at the gate, or show your code to security."
        actions={<Button icon={RefreshCw} onClick={() => { reload(); locate() }}>
          Refresh</Button>} />

      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'checkin', label: 'Check in' },
        { value: 'code', label: 'My code' },
      ]} />

      {tab === 'checkin' ? (
        <div className="grid lg:grid-cols-2 gap-4 mt-4">
          <Card>
            <CardHeader title="Where you are"
              subtitle={g?.branch_name || 'Your branch'}
              action={inRange
                ? <StatusBadge status="At the gate" tone="emerald" dot />
                : <StatusBadge status="Not in range" tone="slate" dot />} />

            <div className="p-5 space-y-4">
              {/* --- the location line ----------------------------------- */}
              <div className="flex items-start gap-3">
                <span className={`h-10 w-10 rounded-xl inline-flex items-center
                  justify-center shrink-0 ${inRange ? 'bg-emerald-50 text-emerald-600'
                    : 'bg-slate-100 text-slate-500'}`}>
                  {locating ? <Loader2 size={18} className="animate-spin" />
                    : <MapPin size={18} />}
                </span>
                <div className="min-w-0 flex-1">
                  {locating ? (
                    <p className="text-sm text-slate-700">Finding your location…</p>
                  ) : locError ? (
                    <p className="text-sm text-slate-700">{locError.message}</p>
                  ) : g?.distance_m != null ? (
                    <>
                      <p className="text-sm text-slate-900">
                        About <span className="font-semibold tnum">
                          {formatDistance(g.distance_m)}</span> from the gate
                      </p>
                      <p className="text-2xs text-slate-500 tnum">
                        Check-in works within {g.radius_m} m
                        {position?.accuracy != null
                          && ` · GPS accurate to ±${Math.round(position.accuracy)} m`}
                      </p>
                    </>
                  ) : (
                    <p className="text-sm text-slate-700">
                      {g?.reason || 'Waiting for your location.'}
                    </p>
                  )}
                </div>
              </div>

              {/* --- why the button is unavailable ----------------------- */}
              {!enabled && g && (
                <InlineAlert tone="info" title="Self check-in is off">
                  {g.reason || 'Your PG has not switched this on. Show your code '
                    + 'to security at the gate instead.'}
                </InlineAlert>
              )}
              {enabled && !inRange && !locating && g?.reason && (
                <InlineAlert tone="warn">{g.reason}</InlineAlert>
              )}
              {locError && (
                <Button icon={RefreshCw} onClick={locate} className="w-full">
                  Try locating again
                </Button>
              )}

              {/* --- the button ------------------------------------------ */}
              <Button variant="primary" icon={ScanLine} loading={busy}
                disabled={!enabled || !inRange || busy}
                onClick={() => setScanning(true)} className="w-full">
                {nextIn ? 'I am at the gate — scan to check in'
                  : 'I am at the gate — scan to check out'}
              </Button>

              <p className="text-2xs text-slate-500 text-center">
                Point your camera at the PGuru code displayed at the gate.
              </p>

              {/* --- outcome --------------------------------------------- */}
              {result && (
                <div className={`rounded-lg border p-4 ${result.allowed
                  ? 'border-emerald-200 bg-emerald-50' : 'border-rose-200 bg-rose-50'}`}>
                  <div className="flex items-start gap-2">
                    {result.allowed
                      ? <CheckCircle2 size={16} className="text-emerald-600 mt-0.5 shrink-0" />
                      : <TriangleAlert size={16} className="text-rose-600 mt-0.5 shrink-0" />}
                    <div className="min-w-0">
                      <p className="text-sm text-slate-900">{result.message}</p>
                      {result.distance_m != null && (
                        <p className="text-2xs text-slate-500 tnum mt-0.5">
                          Recorded {formatDistance(result.distance_m)} from the gate
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </Card>

          <MovementList logs={data.logs} />
        </div>
      ) : (
        <div className="grid lg:grid-cols-2 gap-4 mt-4">
          <Card>
            <CardHeader title="Your code"
              action={<StatusBadge status={data.active ? 'Active' : 'Inactive'}
                tone={data.active ? 'emerald' : 'rose'} dot />} />
            <div className="p-5 flex flex-col items-center gap-4">
              {data.payload ? (
                <>
                  <div className="p-4 rounded-xl border border-line bg-white">
                    <QrCode value={data.payload} size={200} alt="Your gate QR code" />
                  </div>
                  <p className="font-mono text-xs text-slate-500 break-all text-center max-w-xs">
                    {data.token}
                  </p>
                </>
              ) : (
                <EmptyState icon={QrIcon} compact title="No code issued yet"
                  message="Ask the front desk to issue your gate QR." />
              )}
              <InlineAlert tone="info">
                Security can scan this if you cannot check yourself in. It carries
                no personal information — it is a random identifier the gate looks
                up. If you lose your card, ask the office to reissue it.
              </InlineAlert>
            </div>
          </Card>

          <MovementList logs={data.logs} />
        </div>
      )}

      <ScannerModal open={scanning} onClose={() => setScanning(false)}
        onDetect={submit} title="Scan the gate code"
        hint="Hold the code posted at the gate inside the frame." />
    </>
  )
}

function MovementList({ logs }) {
  return (
    <Card>
      <CardHeader title="Recent movements" subtitle={`${logs.length} entries`} />
      {logs.length === 0 ? (
        <EmptyState icon={QrIcon} compact title="No movements recorded" />
      ) : (
        <div className="divide-y divide-line max-h-[520px] overflow-y-auto">
          {logs.map((g) => (
            <div key={g.id} className="px-5 py-3 flex items-center gap-3">
              <span className={`h-8 w-8 rounded-lg inline-flex items-center
                justify-center shrink-0 ${!g.allowed ? 'bg-rose-50 text-rose-600'
                  : g.direction === 'ENTRY' ? 'bg-emerald-50 text-emerald-600'
                    : 'bg-slate-100 text-slate-500'}`}>
                {g.direction === 'ENTRY' ? <LogIn size={15} /> : <LogOut size={15} />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-slate-800">
                  {g.direction === 'ENTRY' ? 'Entered' : 'Left'}
                  {g.gate ? ` · ${g.gate}` : ''}
                  {/* Which route wrote it, so a resident can tell their own
                      check-in from one the desk recorded for them. */}
                  {g.source === 'self' ? ' · self check-in' : ''}
                </p>
                <p className="text-2xs text-slate-500 tnum">
                  {dateTimeFmt(g.occurred_at)}{g.reason ? ` · ${g.reason}` : ''}
                </p>
              </div>
              {!g.allowed && <StatusBadge status="Refused" tone="rose" />}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
