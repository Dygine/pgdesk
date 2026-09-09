import { QrCode, LogIn, LogOut, RefreshCw } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { meApi } from '@/services/api/meApi'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, StatusBadge, EmptyState, Skeleton, InlineAlert, Button,
} from '@/components/ui'
import { relative, dateTimeFmt } from '@/lib/format'

/**
 * The QR is rendered from the token the API returns for this resident only.
 * The token is a random string with no personal information in it, so a
 * photographed code reveals nothing.
 */
function QrCanvas({ value, size = 200 }) {
  // A deterministic dot grid derived from the token. Not a scannable QR
  // symbol - generating a real one needs a library, and the gate reads the
  // token from the card the PG prints. This is the on-screen stand-in.
  const cells = 21
  let hash = 0
  for (let i = 0; i < value.length; i++) hash = (hash * 31 + value.charCodeAt(i)) >>> 0
  const bit = (r, c) => {
    const n = (hash ^ (r * 73856093) ^ (c * 19349663)) >>> 0
    return (n % 7) < 3
  }
  const unit = size / cells
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
      aria-label="Your gate QR code" className="rounded-lg bg-white">
      <rect width={size} height={size} fill="#fff" />
      {Array.from({ length: cells }).map((_, r) =>
        Array.from({ length: cells }).map((_, c) => (
          bit(r, c) ? <rect key={`${r}-${c}`} x={c * unit} y={r * unit}
            width={unit} height={unit} fill="#0F172A" /> : null
        )))}
    </svg>
  )
}

export default function MyScan() {
  const { data, loading, error, reload } = useApi(() => meApi.qr(), [])

  if (error) {
    return (<><PageHeader title="My gate pass" />
      <InlineAlert tone="error" title="Could not load">{error.message}</InlineAlert></>)
  }
  if (loading && !data) {
    return (<><PageHeader title="My gate pass" /><Skeleton className="h-64" /></>)
  }

  return (
    <>
      <PageHeader title="My gate QR"
        subtitle="Show this at the gate. Your entries and exits are listed below."
        actions={<Button icon={RefreshCw} onClick={reload}>Refresh</Button>} />

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Your code"
            action={<StatusBadge status={data.active ? 'Active' : 'Inactive'}
              tone={data.active ? 'emerald' : 'rose'} dot />} />
          <div className="p-5 flex flex-col items-center gap-4">
            {data.token ? (
              <>
                <div className="p-4 rounded-xl border border-line bg-white">
                  <QrCanvas value={data.token} />
                </div>
                <p className="font-mono text-xs text-slate-500 break-all text-center max-w-xs">
                  {data.token}
                </p>
              </>
            ) : (
              <EmptyState icon={QrCode} compact title="No code issued yet"
                message="Ask the front desk to issue your gate QR." />
            )}
            <InlineAlert tone="info">
              This code carries no personal information — it is a random identifier the
              gate looks up. If you lose your card, ask the office to reissue it.
            </InlineAlert>
          </div>
        </Card>

        <Card>
          <CardHeader title="Recent movements" subtitle={`${data.logs.length} entries`} />
          {data.logs.length === 0 ? (
            <EmptyState icon={QrCode} compact title="No movements recorded" />
          ) : (
            <div className="divide-y divide-line max-h-[520px] overflow-y-auto">
              {data.logs.map((g) => (
                <div key={g.id} className="px-5 py-3 flex items-center gap-3">
                  <span className={`h-8 w-8 rounded-lg inline-flex items-center justify-center shrink-0 ${
                    g.direction === 'ENTRY' ? 'bg-emerald-50 text-emerald-600'
                      : 'bg-slate-100 text-slate-500'}`}>
                    {g.direction === 'ENTRY' ? <LogIn size={15} /> : <LogOut size={15} />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-slate-800">
                      {g.direction === 'ENTRY' ? 'Entered' : 'Left'}
                      {g.gate ? ` · ${g.gate}` : ''}
                    </p>
                    <p className="text-2xs text-slate-500 tnum">{dateTimeFmt(g.occurred_at)}</p>
                  </div>
                  {!g.allowed && <StatusBadge status="Refused" tone="rose" />}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
